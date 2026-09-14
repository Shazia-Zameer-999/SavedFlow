"""Action management API (section 19, endpoints in section 41)."""
from flask import Blueprint, jsonify, request

from extensions import get_db
from models.action import ACTION_STATUSES, new_action
from routes.items import _find_item_or_404, _object_id_or_404
from utils.dates import utcnow
from utils.errors import ApiError
from utils.json_utils import serialize_doc
from utils.validation import require_fields, require_json_body

actions_bp = Blueprint("actions", __name__)


@actions_bp.route("/api/actions", methods=["GET"])
def list_actions():
    db = get_db()
    query = {}
    if request.args.get("status"):
        query["status"] = request.args["status"]
    if request.args.get("item_id"):
        query["item_id"] = _object_id_or_404(request.args["item_id"])
    actions = list(db.actions.find(query).sort("created_at", -1))
    return jsonify({"success": True, "actions": serialize_doc(actions)})


@actions_bp.route("/api/actions", methods=["POST"])
def create_action():
    db = get_db()
    data = require_json_body(request)
    require_fields(data, ["item_id", "title"])

    item_oid = _object_id_or_404(data["item_id"])
    _find_item_or_404(db, str(item_oid))  # ensures the referenced item exists

    action = new_action(
        item_id=item_oid,
        title=data["title"],
        description=data.get("description", ""),
        priority=data.get("priority", "MEDIUM"),
        due_date=data.get("due_date"),
    )
    inserted = db.actions.insert_one(action)
    action["_id"] = inserted.inserted_id
    return jsonify({"success": True, "action": serialize_doc(action)}), 201


@actions_bp.route("/api/actions/<action_id>", methods=["GET"])
def get_action(action_id):
    db = get_db()
    oid = _object_id_or_404(action_id)
    action = db.actions.find_one({"_id": oid})
    if not action:
        raise ApiError("ACTION_NOT_FOUND", f"No action found with id '{action_id}'.", 404)
    return jsonify({"success": True, "action": serialize_doc(action)})


@actions_bp.route("/api/actions/<action_id>", methods=["PATCH"])
def update_action(action_id):
    db = get_db()
    oid = _object_id_or_404(action_id)
    action = db.actions.find_one({"_id": oid})
    if not action:
        raise ApiError("ACTION_NOT_FOUND", f"No action found with id '{action_id}'.", 404)

    data = require_json_body(request)
    updatable_fields = {"title", "description", "priority", "status", "due_date", "notes", "result", "rating"}
    updates = {k: v for k, v in data.items() if k in updatable_fields}

    if "status" in updates and updates["status"] not in ACTION_STATUSES:
        raise ApiError("INVALID_STATUS", f"status must be one of {sorted(ACTION_STATUSES)}.", 400)

    if not updates:
        raise ApiError("NO_UPDATABLE_FIELDS", "No updatable fields were provided.", 400)

    updates["updated_at"] = utcnow()
    if updates.get("status") == "COMPLETED" and not action.get("completed_at"):
        updates["completed_at"] = utcnow()

    db.actions.update_one({"_id": oid}, {"$set": updates})
    updated = db.actions.find_one({"_id": oid})
    return jsonify({"success": True, "action": serialize_doc(updated)})
