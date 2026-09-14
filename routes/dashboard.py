"""GET /api/dashboard (section 29) - entirely derived from MongoDB data."""
from flask import Blueprint, jsonify

from extensions import get_db
from services.ai.recommendations import recommend_general
from utils.json_utils import serialize_doc

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/api/dashboard", methods=["GET"])
def dashboard():
    db = get_db()
    items = db.instagram_items

    data = {
        "total_items": items.count_documents({}),
        "unwatched": items.count_documents({"watch_count": 0}),
        "watched": items.count_documents({"watch_count": {"$gt": 0}}),
        "ai_analyzed": items.count_documents({"analysis_status": "COMPLETED"}),
        "analysis_pending": items.count_documents({"analysis_status": {"$in": ["QUEUED", "PROCESSING"]}}),
        "worth_watching": items.count_documents({"recommendation": {"$in": ["WATCH_NOW", "WATCH_LATER"]}}),
        "worth_implementing": items.count_documents({"recommendation": "WORTH_IMPLEMENTING"}),
        "applied": items.count_documents({"status": "APPLIED"}),
        "not_useful": items.count_documents({"status": "NOT_USEFUL"}),
        "archived": items.count_documents({"status": "ARCHIVED"}),
        "pending_actions": db.actions.count_documents({"status": {"$in": ["NOT_STARTED", "PLANNED", "IN_PROGRESS"]}}),
    }

    top_recs = recommend_general(db, limit=5)
    data["top_recommendations"] = [
        {"item_id": str(r["item"]["_id"]), "score": r["score"], "reason": r["reason"]} for r in top_recs
    ]
    data["recently_imported"] = serialize_doc(list(items.find().sort("imported_at", -1).limit(5)))
    data["recently_watched"] = serialize_doc(
        list(items.find({"last_watched_at": {"$ne": None}}).sort("last_watched_at", -1).limit(5))
    )
    data["recently_applied"] = serialize_doc(
        list(items.find({"applied_at": {"$ne": None}}).sort("applied_at", -1).limit(5))
    )

    return jsonify({"success": True, **data})
