"""
Item management API (section 26) plus watch/apply tracking (sections
24-25), which live here since they act on an existing item.
"""
from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, jsonify, request

from extensions import get_db
from models.item import ITEM_STATUSES, PRIORITIES, new_item
from utils.dates import utcnow
from utils.errors import ApiError
from utils.json_utils import serialize_doc
from utils.urls import is_valid_instagram_url, normalize_instagram_url
from utils.validation import parse_pagination, require_json_body

items_bp = Blueprint("items", __name__)


def _object_id_or_404(item_id):
    try:
        return ObjectId(item_id)
    except (InvalidId, TypeError):
        raise ApiError("INVALID_ITEM_ID", f"'{item_id}' is not a valid item id.", 400)


def _find_item_or_404(db, item_id):
    oid = _object_id_or_404(item_id)
    item = db.instagram_items.find_one({"_id": oid})
    if not item:
        raise ApiError("ITEM_NOT_FOUND", f"No item found with id '{item_id}'.", 404)
    return item


@items_bp.route("/api/items", methods=["GET"])
def list_items():
    db = get_db()
    query = {}

    if request.args.get("status"):
        query["status"] = request.args["status"]
    if request.args.get("category"):
        query["category"] = request.args["category"]
    if request.args.get("recommendation"):
        query["recommendation"] = request.args["recommendation"]
    if request.args.get("watched") is not None and request.args.get("watched") != "":
        watched = request.args["watched"].lower() == "true"
        query["watch_count"] = {"$gt": 0} if watched else 0
    if request.args.get("min_score"):
        try:
            query["usefulness_score"] = {"$gte": int(request.args["min_score"])}
        except ValueError:
            raise ApiError("INVALID_QUERY_PARAM", "min_score must be an integer.", 400)
    if request.args.get("search"):
        term = request.args["search"]
        query["$or"] = [
            {"caption": {"$regex": term, "$options": "i"}},
            {"creator_username": {"$regex": term, "$options": "i"}},
            {"user_notes": {"$regex": term, "$options": "i"}},
        ]

    sort_field_map = {
        "usefulness": "usefulness_score",
        "created_at": "created_at",
        "development_relevance": "development_relevance_score",
    }
    sort_key = sort_field_map.get(request.args.get("sort"), "created_at")
    sort_direction = -1

    page, page_size = parse_pagination(request.args)

    cursor = (
        db.instagram_items.find(query)
        .sort(sort_key, sort_direction)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    total = db.instagram_items.count_documents(query)

    return jsonify({
        "success": True,
        "items": serialize_doc(list(cursor)),
        "pagination": {"page": page, "page_size": page_size, "total": total},
    })


@items_bp.route("/api/items/<item_id>", methods=["GET"])
def get_item(item_id):
    db = get_db()
    item = _find_item_or_404(db, item_id)
    return jsonify({"success": True, "item": serialize_doc(item)})


@items_bp.route("/api/items", methods=["POST"])
def create_item():
    db = get_db()
    data = require_json_body(request)
    url = data.get("url")
    if not url or not is_valid_instagram_url(url):
        raise ApiError("INVALID_INSTAGRAM_URL", "The supplied URL is not a valid Instagram URL.", 400)

    normalized = normalize_instagram_url(url)
    if db.instagram_items.find_one({"normalized_url": normalized}):
        raise ApiError("DUPLICATE_URL", "This URL has already been imported.", 409)

    item = new_item(
        url=url,
        normalized_url=normalized,
        source_method="MANUAL",
        creator_username=data.get("creator_username"),
        caption=data.get("caption"),
        media_type=data.get("media_type"),
    )
    if data.get("category"):
        item["category"] = data["category"]
    if data.get("tags"):
        item["tags"] = data["tags"]
    if data.get("user_notes"):
        item["user_notes"] = data["user_notes"]
    if data.get("why_saved"):
        item["why_saved"] = data["why_saved"]

    inserted = db.instagram_items.insert_one(item)
    item["_id"] = inserted.inserted_id
    return jsonify({"success": True, "item": serialize_doc(item)}), 201


@items_bp.route("/api/items/<item_id>", methods=["PATCH"])
def update_item(item_id):
    db = get_db()
    item = _find_item_or_404(db, item_id)
    data = require_json_body(request)

    updatable_fields = {
        "status", "priority", "category", "tags", "user_notes",
        "why_saved", "creator_username", "caption",
    }
    updates = {k: v for k, v in data.items() if k in updatable_fields}

    if "status" in updates and updates["status"] not in ITEM_STATUSES:
        raise ApiError("INVALID_STATUS", f"status must be one of {sorted(ITEM_STATUSES)}.", 400)
    if "priority" in updates and updates["priority"] not in PRIORITIES:
        raise ApiError("INVALID_PRIORITY", f"priority must be one of {sorted(PRIORITIES)}.", 400)

    if not updates:
        raise ApiError("NO_UPDATABLE_FIELDS", "No updatable fields were provided.", 400)

    updates["updated_at"] = utcnow()
    db.instagram_items.update_one({"_id": item["_id"]}, {"$set": updates})
    updated = db.instagram_items.find_one({"_id": item["_id"]})
    return jsonify({"success": True, "item": serialize_doc(updated)})


@items_bp.route("/api/items/<item_id>", methods=["DELETE"])
def delete_item(item_id):
    db = get_db()
    item = _find_item_or_404(db, item_id)
    db.instagram_items.delete_one({"_id": item["_id"]})
    return jsonify({"success": True, "deleted_id": item_id})


@items_bp.route("/api/items/<item_id>/watch", methods=["POST"])
def watch_item(item_id):
    """POST /api/items/<id>/watch (section 24)."""
    db = get_db()
    item = _find_item_or_404(db, item_id)
    now = utcnow()

    updates = {
        "watch_count": (item.get("watch_count") or 0) + 1,
        "last_watched_at": now,
        "updated_at": now,
    }
    if not item.get("watched_at"):
        updates["watched_at"] = now
    if item.get("status") == "UNWATCHED":
        updates["status"] = "WATCHED"

    db.instagram_items.update_one({"_id": item["_id"]}, {"$set": updates})
    updated = db.instagram_items.find_one({"_id": item["_id"]})
    return jsonify({"success": True, "item": serialize_doc(updated)})


@items_bp.route("/api/items/<item_id>/apply", methods=["POST"])
def apply_item(item_id):
    """POST /api/items/<id>/apply (section 25)."""
    db = get_db()
    item = _find_item_or_404(db, item_id)
    data = request.get_json(silent=True) or {}
    now = utcnow()

    updates = {"status": "APPLIED", "applied_at": now, "updated_at": now}
    if data.get("implementation_notes"):
        updates["user_notes"] = (item.get("user_notes", "") + "\n" + data["implementation_notes"]).strip()

    db.instagram_items.update_one({"_id": item["_id"]}, {"$set": updates})

    created_action_id = None
    if data.get("create_action"):
        from models.action import new_action
        action = new_action(
            item_id=item["_id"],
            title=data.get("action_title") or f"Implement idea from @{item.get('creator_username') or 'saved item'}",
            description=data.get("implementation_notes", ""),
        )
        inserted = db.actions.insert_one(action)
        created_action_id = str(inserted.inserted_id)

    updated = db.instagram_items.find_one({"_id": item["_id"]})
    return jsonify({
        "success": True,
        "item": serialize_doc(updated),
        "created_action_id": created_action_id,
    })
