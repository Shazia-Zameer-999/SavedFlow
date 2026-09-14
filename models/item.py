"""
Instagram item schema (section 8.1) and status/enums (section 9).

These are plain functions that build/validate dicts - not a heavyweight
ORM - which keeps the project easy to follow for someone learning from it.
"""
from utils.dates import utcnow

MEDIA_STATUSES = {"AVAILABLE", "UNAVAILABLE", "UNKNOWN"}
ANALYSIS_STATUSES = {"NOT_ANALYZED", "QUEUED", "PROCESSING", "COMPLETED", "FAILED", "NOT_AVAILABLE"}
ITEM_STATUSES = {"UNWATCHED", "WATCHED", "WORTH_TRYING", "APPLIED", "NOT_USEFUL", "ARCHIVED"}
PRIORITIES = {"LOW", "MEDIUM", "HIGH"}
SOURCE_METHODS = {"API", "EXPORT", "MANUAL", "LOCAL_BROWSER"}
RECOMMENDATIONS = {"WATCH_NOW", "WATCH_LATER", "WORTH_IMPLEMENTING", "LOW_VALUE", "SKIP", None}


def new_item(
    url,
    normalized_url,
    source_method="MANUAL",
    instagram_media_id=None,
    creator_username=None,
    caption=None,
    media_type=None,
    media_status="UNKNOWN",
    saved_at=None,
    source_metadata=None,
):
    now = utcnow()
    return {
        "source": "instagram",
        "instagram_media_id": instagram_media_id,
        "url": url,
        "normalized_url": normalized_url,
        "creator_username": creator_username,
        "caption": caption,
        "media_type": media_type,
        "media_status": media_status if media_status in MEDIA_STATUSES else "UNKNOWN",
        "source_method": source_method if source_method in SOURCE_METHODS else "MANUAL",
        "saved_at": saved_at,
        "source_metadata": source_metadata or {},
        "imported_at": now,
        "status": "UNWATCHED",
        "watched_at": None,
        "watch_count": 0,
        "last_watched_at": None,
        "applied_at": None,
        "priority": "MEDIUM",
        "category": None,
        "tags": [],
        "user_notes": "",
        "why_saved": "",
        "ai_analysis_id": None,
        "analysis_status": "NOT_ANALYZED",
        "usefulness_score": None,
        "development_relevance_score": None,
        "implementation_value_score": None,
        "learning_value_score": None,
        "recommendation": None,
        "created_at": now,
        "updated_at": now,
    }
