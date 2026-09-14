"""
Central place for the MongoDB connection.

Using mongomock in tests means the exact same code path (get_db()) works
against a real MongoDB server in dev/prod and against an in-memory fake in
tests - no test-only branching scattered through the app.
"""
import mongomock
from pymongo import MongoClient
from utils.urls import normalize_instagram_url

_client = None
_db = None
_using_mock = False


def init_db(app):
    """Initialize the MongoDB connection for the given Flask app config."""
    global _client, _db, _using_mock

    if app.config.get("TESTING"):
        _client = mongomock.MongoClient()
        _using_mock = True
    else:
        _client = MongoClient(app.config["MONGO_URI"], serverSelectionTimeoutMS=3000)
        _using_mock = False

    _db = _client[app.config["MONGO_DB_NAME"]]

    try:
        _create_indexes(_db)
    except Exception as exc: 
        app.logger.warning("Could not create MongoDB indexes at startup: %s", exc)

    return _db


def get_db():
    if _db is None:
        raise RuntimeError("Database not initialized - call init_db(app) first.")
    return _db


def is_using_mock():
    return _using_mock


def check_connection():
    """Return True/False for whether the database is reachable."""
    try:
        _client.admin.command("ping")
        return True
    except Exception:
        return False


def _create_indexes(db):
    items = db.instagram_items

    for item in items.find({"url": {"$type": "string"}}):
        normalized = normalize_instagram_url(item["url"])
        if normalized and item.get("normalized_url") != normalized:
            items.update_one({"_id": item["_id"]}, {"$set": {"normalized_url": normalized}})
    try:
        items.drop_index("permalink_1")
    except Exception:
        pass
    items.create_index("normalized_url", unique=True, sparse=True)
    # Only real media IDs should participate in uniqueness. A nullable field
    # must not make every URL without an API media ID collide with one another.
    try:
        items.drop_index("instagram_media_id_1")
    except Exception:
        pass
    items.create_index(
        "instagram_media_id",
        unique=True,
        partialFilterExpression={"instagram_media_id": {"$type": "string"}},
    )
    items.create_index("status")
    items.create_index("analysis_status")
    items.create_index("category")
    items.create_index("tags")
    items.create_index("created_at")
    items.create_index("usefulness_score")
    items.create_index("development_relevance_score")
    items.create_index("recommendation")

    db.actions.create_index("item_id")
    db.actions.create_index("status")

    db.ai_jobs.create_index("item_id")
    db.ai_jobs.create_index("status")

    db.ai_analyses.create_index("item_id")

    db.user_preferences.create_index("topic", unique=True)

    db.weekly_reviews.create_index("created_at")
    db.sync_jobs.create_index("status")
    db.sync_jobs.create_index("created_at")
