"""
Application configuration loaded from environment variables.

No secret ever has a hardcoded fallback value that looks like a real
credential - missing values are simply left empty/None and features that
depend on them report themselves as "not configured" rather than failing
silently or pretending to work.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    FLASK_ENV = os.environ.get("FLASK_ENV", "development")
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-not-for-production")

    MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "savedflow")

    META_APP_ID = os.environ.get("META_APP_ID", "")
    META_APP_SECRET = os.environ.get("META_APP_SECRET", "")
    META_ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN", "")
    INSTAGRAM_ACCOUNT_ID = os.environ.get("INSTAGRAM_ACCOUNT_ID", "")

    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

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
