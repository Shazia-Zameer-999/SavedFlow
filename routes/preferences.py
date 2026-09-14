"""Preference endpoints (section 15, endpoints referenced in section 41)."""
from flask import Blueprint, jsonify, request

from extensions import get_db
from utils.errors import ApiError
from utils.json_utils import serialize_doc
from utils.validation import require_json_body
from services.ai.recommendations import update_preference_from_feedback

preferences_bp = Blueprint("preferences", __name__)


@preferences_bp.route("/api/preferences", methods=["GET"])
def list_preferences():
    db = get_db()
    prefs = list(db.user_preferences.find().sort("weight", -1))
    return jsonify({"success": True, "preferences": serialize_doc(prefs)})


@preferences_bp.route("/api/preferences", methods=["PATCH"])
def update_preference():
    """
    Body: {"topic": "MongoDB", "was_useful": true}
    or directly: {"topic": "MongoDB", "weight": 0.9}
    """
    db = get_db()
    data = require_json_body(request)
    topic = data.get("topic")
    if not topic:
        raise ApiError("MISSING_FIELDS", "Missing required field: topic.", 400)

    if "weight" in data:
        try:
            weight = float(data["weight"])
        except (TypeError, ValueError):
            raise ApiError("INVALID_WEIGHT", "weight must be a number between 0 and 1.", 400)
        weight = max(0.0, min(1.0, weight))
        from utils.dates import utcnow
        db.user_preferences.update_one(
            {"topic": topic},
            {"$set": {"weight": weight, "updated_at": utcnow()},
             "$setOnInsert": {"topic": topic, "created_at": utcnow()}},
            upsert=True,
        )
        new_weight = weight
    elif "was_useful" in data:
        new_weight = update_preference_from_feedback(db, topic, bool(data["was_useful"]))
    else:
        raise ApiError("MISSING_FIELDS", "Provide either 'weight' or 'was_useful'.", 400)

    pref = db.user_preferences.find_one({"topic": topic})
    return jsonify({"success": True, "preference": serialize_doc(pref)})
