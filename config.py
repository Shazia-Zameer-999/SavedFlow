"""
Application configuration loaded from environment variables.

No secret ever has a hardcoded fallback value that looks like a real
credential. Missing values are left empty and features that depend on them
report themselves as not configured.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    FLASK_ENV = os.environ.get("FLASK_ENV", "development")
    SECRET_KEY = os.environ.get(
        "FLASK_SECRET_KEY",
        "dev-secret-key-not-for-production",
    )

    MONGO_URI = os.environ.get(
        "MONGO_URI",
        "mongodb://localhost:27017",
    )
    MONGO_DB_NAME = os.environ.get(
        "MONGO_DB_NAME",
        "savedflow",
    )

    META_APP_ID = os.environ.get("META_APP_ID", "")
    META_APP_SECRET = os.environ.get("META_APP_SECRET", "")
    META_ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN", "")
    INSTAGRAM_ACCOUNT_ID = os.environ.get("INSTAGRAM_ACCOUNT_ID", "")

    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.environ.get(
        "GEMINI_MODEL",
        "gemini-2.5-flash",
    )
    GEMINI_DAILY_REQUEST_LIMIT = int(os.environ.get("GEMINI_DAILY_REQUEST_LIMIT", "20"))
    GEMINI_MIN_RETRY_DELAY_SECONDS = int(
        os.environ.get("GEMINI_MIN_RETRY_DELAY_SECONDS", "300")
    )

    # Local Instagram sync configuration.
    #
    # SAVEDFLOW_SERVER_URL:
    # The URL where the local sync helper sends discovered items.
    #
    # Example local development:
    # http://127.0.0.1:5002
    #
    # Example production:
    # https://your-savedflow.vercel.app
    SAVEDFLOW_SERVER_URL = os.environ.get(
        "SAVEDFLOW_SERVER_URL",
        "",
    )

    # URL of the Instagram Saved collection that should be synchronized.
    INSTAGRAM_SAVED_URL = os.environ.get(
        "INSTAGRAM_SAVED_URL",
        "",
    )

    # Secret used only by the local sync agent when communicating with
    # SavedFlow. Never expose this value to the frontend.
    SAVEDFLOW_SYNC_TOKEN = os.environ.get(
        "SAVEDFLOW_SYNC_TOKEN",
        "",
    )
    GITHUB_ACTIONS_TOKEN = os.environ.get(
        "GITHUB_ACTIONS_TOKEN",
        "",
    )
    SAVEDFLOW_WORKER_TOKEN = os.environ.get(
        "SAVEDFLOW_WORKER_TOKEN",
        "",
    )
    # Local-only profile used by the persistent worker for requested evidence
    # capture. The profile path and its cookies are never sent to Flask clients.
    INSTAGRAM_BROWSER_PROFILE = os.environ.get(
        "INSTAGRAM_BROWSER_PROFILE",
        "",
    )
    AI_JOB_MAX_RETRIES = int(os.environ.get("AI_JOB_MAX_RETRIES", "3"))
    AI_JOB_STALE_TIMEOUT_SECONDS = int(
        os.environ.get("AI_JOB_STALE_TIMEOUT_SECONDS", "1800")
    )

    # How often the local sync agent checks for a requested sync.
    SYNC_INTERVAL_SECONDS = int(os.environ.get("SYNC_INTERVAL_SECONDS", "60"))

    TESTING = False

    @classmethod
    def instagram_configured(cls):
        return bool(cls.META_ACCESS_TOKEN and cls.INSTAGRAM_ACCOUNT_ID)

    @classmethod
    def ai_configured(cls):
        return bool(cls.GEMINI_API_KEY)


class TestConfig(Config):
    TESTING = True
    MONGO_DB_NAME = "savedflow_test"
    SAVEDFLOW_SYNC_TOKEN = "test-sync-token"
    SAVEDFLOW_WORKER_TOKEN = "test-worker-token"
