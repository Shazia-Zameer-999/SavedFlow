"""Recommendation endpoints (sections 16-18)."""
from flask import Blueprint, jsonify, request

from extensions import get_db
from services.ai.recommendations import recommend_general, recommend_implement_next, recommend_watch_next
from utils.json_utils import serialize_doc

recommendations_bp = Blueprint("recommendations", __name__)


def _limit_from_args():
    try:
        return max(1, min(int(request.args.get("limit", 20)), 100))
    except (TypeError, ValueError):
        return 20


def _format(entries):
    out = []
    for entry in entries:
        item = serialize_doc(entry["item"])
        formatted = {"item_id": item["id"], "item": item, "score": entry["score"], "reason": entry["reason"]}
        if "suggested_action" in entry:
            formatted["suggested_action"] = entry["suggested_action"]
        out.append(formatted)
    return out


@recommendations_bp.route("/api/recommendations", methods=["GET"])
def get_recommendations():
    db = get_db()
    results = recommend_general(db, limit=_limit_from_args())
    return jsonify({"success": True, "recommendations": _format(results)})


@recommendations_bp.route("/api/recommendations/watch", methods=["GET"])
def get_watch_recommendations():
    db = get_db()
    results = recommend_watch_next(db, limit=_limit_from_args())
    return jsonify({"success": True, "category": "WATCH_NEXT", "recommendations": _format(results)})


@recommendations_bp.route("/api/recommendations/implement", methods=["GET"])
def get_implement_recommendations():
    db = get_db()
    results = recommend_implement_next(db, limit=_limit_from_args())
    return jsonify({"success": True, "category": "IMPLEMENT_NEXT", "recommendations": _format(results)})
