"""AI job schema (section 22)."""
from utils.dates import utcnow

JOB_STATUSES = {"QUEUED", "PROCESSING", "COMPLETED", "FAILED"}


def new_job(item_id, job_type="ANALYZE"):
    now = utcnow()
    return {
        "item_id": item_id,
        "job_type": job_type,
        "status": "QUEUED",
        "created_at": now,
        "started_at": None,
        "completed_at": None,
        "error": None,
    }
