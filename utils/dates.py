"""Small date/time helpers - always UTC, always ISO 8601 strings for JSON output."""
from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc)


def to_iso(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()
