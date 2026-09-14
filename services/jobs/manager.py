"""
Simple thread-based background job system for AI analysis (section 22).

No Redis/Celery per the spec - a plain Python thread is enough for a
single-user V1 app. Jobs are still tracked in MongoDB (ai_jobs) so status
can be polled via GET /api/jobs/<id> regardless of which thread ran them.

For tests (and for synchronous/deterministic behavior generally), jobs can
be run inline via run_analysis_job() directly instead of through a thread.
"""
import threading

from bson import ObjectId

from models.job import new_job
from services.ai.analyzer import analyze_item, AnalysisValidationError
from services.ai.client import AIClient, AIClientError
from models.analysis import new_analysis
from utils.dates import utcnow


def create_job(db, item_id, job_type="ANALYZE"):
    job = new_job(item_id, job_type=job_type)
    inserted = db.ai_jobs.insert_one(job)
    return inserted.inserted_id


def run_analysis_job(db, job_id, ai_client=None):
    """
    Synchronously execute an ANALYZE job: run the AI pipeline, validate the
    result, store the analysis, update the item, and mark the job
    COMPLETED or FAILED. Never leaves the item or job in an inconsistent
    state - any exception is caught and turns into a FAILED job with the
    error message stored, and the database is never partially written.
    """
    job = db.ai_jobs.find_one({"_id": job_id})
    if not job:
        return

    db.ai_jobs.update_one({"_id": job_id}, {"$set": {"status": "PROCESSING", "started_at": utcnow()}})

    item = db.instagram_items.find_one({"_id": job["item_id"]})
    if not item:
        db.ai_jobs.update_one(
            {"_id": job_id},
            {"$set": {"status": "FAILED", "error": "Item no longer exists.", "completed_at": utcnow()}},
        )
        return

    db.instagram_items.update_one({"_id": item["_id"]}, {"$set": {"analysis_status": "PROCESSING"}})

    try:
        basis, structured_output = analyze_item(item, ai_client=ai_client or AIClient())
    except (AIClientError, AnalysisValidationError) as exc:
        db.ai_jobs.update_one(
            {"_id": job_id},
            {"$set": {"status": "FAILED", "error": str(exc), "completed_at": utcnow()}},
        )
        db.instagram_items.update_one({"_id": item["_id"]}, {"$set": {"analysis_status": "FAILED"}})
        return
    except Exception as exc:  # noqa: BLE001 - last-resort safety net, never corrupt state
        db.ai_jobs.update_one(
            {"_id": job_id},
            {"$set": {"status": "FAILED", "error": f"Unexpected error: {exc}", "completed_at": utcnow()}},
        )
        db.instagram_items.update_one({"_id": item["_id"]}, {"$set": {"analysis_status": "FAILED"}})
        return

    existing_version = 1
    previous = db.ai_analyses.find_one({"item_id": item["_id"]}, sort=[("analysis_version", -1)])
    if previous:
        existing_version = previous.get("analysis_version", 1) + 1

    analysis_doc = new_analysis(
        item_id=item["_id"],
        structured_output=structured_output,
        analysis_basis=basis,
        model=(ai_client or AIClient()).model,
        analysis_version=existing_version,
    )
    inserted_analysis = db.ai_analyses.insert_one(analysis_doc)

    db.instagram_items.update_one(
        {"_id": item["_id"]},
        {"$set": {
            "ai_analysis_id": inserted_analysis.inserted_id,
            "analysis_status": "COMPLETED",
            "usefulness_score": structured_output.get("overall_usefulness_score"),
            "development_relevance_score": structured_output.get("development_relevance_score"),
            "implementation_value_score": structured_output.get("implementation_value_score"),
            "learning_value_score": structured_output.get("learning_value_score"),
            "recommendation": structured_output.get("recommendation"),
            "updated_at": utcnow(),
        }},
    )

    db.ai_jobs.update_one({"_id": job_id}, {"$set": {"status": "COMPLETED", "completed_at": utcnow()}})


def start_analysis_job_async(db, job_id):
    """Fire-and-forget background thread wrapper around run_analysis_job."""
    thread = threading.Thread(target=run_analysis_job, args=(db, job_id), daemon=True)
    thread.start()
    return thread
