"""
Weekly review (section 21).

The review is built entirely from real database aggregates - counts,
top-scored items, categories - never invented. If OPENAI_API_KEY is
configured, the AI is used only to turn those real numbers into readable
prose (and is explicitly told not to add facts beyond what's given); if
not configured, a straightforward templated summary is returned instead so
the feature still works without an AI key.
"""
import json
from datetime import timedelta

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, jsonify, request

from extensions import get_db
from services.ai.client import AIClient, AIClientError
from utils.dates import utcnow
from utils.errors import ApiError
from utils.json_utils import serialize_doc

reviews_bp = Blueprint("reviews", __name__)

REVIEW_SUMMARY_SYSTEM_PROMPT = (
    "You write a short, friendly weekly review for a developer based ONLY on "
    "the real statistics provided to you as JSON. Do not invent any numbers, "
    "items, or activity not present in the data. Return a JSON object: "
    '{"narrative_summary": string}.'
)


def _gather_review_data(db, since):
    items = db.instagram_items
    imported = list(items.find({"imported_at": {"$gte": since}}))
    watched = list(items.find({"last_watched_at": {"$gte": since}}))
    applied = list(items.find({"applied_at": {"$gte": since}}))

    analyzed_with_scores = list(
        items.find({"analysis_status": "COMPLETED", "usefulness_score": {"$ne": None}})
        .sort("usefulness_score", -1)
        .limit(5)
    )

    topics = {}
    for item in items.find({"category": {"$ne": None}}):
        topics[item["category"]] = topics.get(item["category"], 0) + 1
    top_categories = sorted(topics.items(), key=lambda kv: kv[1], reverse=True)[:5]

    archivable = list(items.find({"status": {"$in": ["NOT_USEFUL"]}}).limit(10))

    watch_recs = list(items.find({"recommendation": {"$in": ["WATCH_NOW", "WATCH_LATER"]}}).limit(5))
    implement_recs = list(items.find({"recommendation": "WORTH_IMPLEMENTING"}).limit(5))

    return {
        "period_start": since.isoformat(),
        "period_end": utcnow().isoformat(),
        "items_imported": len(imported),
        "items_watched": len(watched),
        "items_applied": len(applied),
        "best_saved_content": serialize_doc(analyzed_with_scores),
        "top_categories": [{"category": c, "count": n} for c, n in top_categories],
        "top_items_to_watch": serialize_doc(watch_recs),
        "top_items_to_implement": serialize_doc(implement_recs),
        "items_worth_archiving": serialize_doc(archivable),
    }


@reviews_bp.route("/api/weekly-review", methods=["POST"])
def create_weekly_review():
    db = get_db()
    since = utcnow() - timedelta(days=7)
    data = _gather_review_data(db, since)

    narrative_summary = None
    ai_client = AIClient()
    if ai_client.is_configured():
        try:
            raw = ai_client.complete_json(
                REVIEW_SUMMARY_SYSTEM_PROMPT,
                f"Real weekly statistics (JSON, do not add anything not present here):\n{json.dumps(data, default=str)}",
            )
            parsed = ai_client.parse_json(raw)
            narrative_summary = parsed.get("narrative_summary")
        except AIClientError:
            narrative_summary = None

    if not narrative_summary:
        narrative_summary = (
            f"This week you imported {data['items_imported']} item(s), watched "
            f"{data['items_watched']}, and applied {data['items_applied']}. "
            f"{'Your top category was ' + data['top_categories'][0]['category'] + '.' if data['top_categories'] else ''}"
        ).strip()

    review_doc = {**data, "narrative_summary": narrative_summary, "created_at": utcnow()}
    inserted = db.weekly_reviews.insert_one(review_doc)
    review_doc["_id"] = inserted.inserted_id

    return jsonify({"success": True, "review": serialize_doc(review_doc)}), 201


@reviews_bp.route("/api/weekly-review/<review_id>", methods=["GET"])
def get_weekly_review(review_id):
    db = get_db()
    try:
        oid = ObjectId(review_id)
    except (InvalidId, TypeError):
        raise ApiError("INVALID_REVIEW_ID", f"'{review_id}' is not a valid review id.", 400)
    review = db.weekly_reviews.find_one({"_id": oid})
    if not review:
        raise ApiError("REVIEW_NOT_FOUND", f"No weekly review found with id '{review_id}'.", 404)
    return jsonify({"success": True, "review": serialize_doc(review)})
