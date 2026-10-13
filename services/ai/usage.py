"""Atomic daily accounting for outbound Gemini requests."""

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from config import Config
from utils.dates import utcnow


class GeminiDailyLimitExceeded(Exception):
    """Raised when the configured daily Gemini request budget is exhausted."""


def reserve_gemini_request(db):
    limit = Config.GEMINI_DAILY_REQUEST_LIMIT
    if limit < 1:
        raise GeminiDailyLimitExceeded("GEMINI_DAILY_REQUEST_LIMIT must be at least 1.")

    now = utcnow()
    day = now.date().isoformat()
    try:
        usage = db.ai_usage.find_one_and_update(
            {"date": day, "count": {"$lt": limit}},
            {
                "$inc": {"count": 1},
                "$set": {"updated_at": now},
                "$setOnInsert": {"date": day, "created_at": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        usage = None
    if usage is None:
        raise GeminiDailyLimitExceeded(
            f"The daily Gemini request limit of {limit} has been reached."
        )
    return usage["count"]
