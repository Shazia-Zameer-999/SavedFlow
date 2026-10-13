"""AI job schema (section 22)."""

from utils.dates import utcnow

JOB_STATUSES = {
    "QUEUED",
    "WAITING_FOR_QUOTA",
    "RETRY_WAIT",
    "PROCESSING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
}


def new_job(item_id, job_type="ANALYZE", retry_of=None, retry_count=0):
    now = utcnow()
    return {
        "item_id": item_id,
        "job_type": job_type,
        "status": "QUEUED",
        "stage": "QUEUED",
        "created_at": now,
        "started_at": None,
        "completed_at": None,
        "attempt_count": 0,
        "retry_after": None,
        "error": None,
        "retry_of": retry_of,
        "retry_count": retry_count,
    }
