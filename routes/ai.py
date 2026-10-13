"""
AI analysis + job endpoints (sections 22-23).

POST /api/items/<id>/analyze creates a job and either runs it inline
(TESTING/no background thread desired) or kicks off a background thread,
then returns the job immediately (202) so the HTTP request never blocks
on the AI call.
"""

from flask import Blueprint, current_app, jsonify, request

from extensions import get_db
from config import Config
from models.job import JOB_STATUSES
from routes.items import _find_item_or_404, _object_id_or_404
from services.jobs.manager import claim_next_job, create_job, run_analysis_job
from utils.errors import ApiError
from utils.json_utils import serialize_doc

ai_bp = Blueprint("ai", __name__)


def _start_job(db, item_id_oid, reanalyze=False):
    job_id = create_job(
        db, item_id_oid, job_type="REANALYZE" if reanalyze else "ANALYZE"
    )
    job = db.ai_jobs.find_one({"_id": job_id})
    item_status = (
        "WAITING_FOR_QUOTA"
        if job and job.get("status") == "WAITING_FOR_QUOTA"
        else "QUEUED"
    )
    db.instagram_items.update_one(
        {"_id": item_id_oid}, {"$set": {"analysis_status": item_status}}
    )
    return job_id


@ai_bp.route("/api/items/<item_id>/analyze", methods=["POST"])
def analyze_item_route(item_id):
    db = get_db()
    item = _find_item_or_404(db, item_id)

    if item.get("analysis_status") == "COMPLETED":
        return jsonify(
            {
                "success": True,
                "message": "Item already analyzed. Use /reanalyze to force a new analysis.",
                "item": serialize_doc(item),
            }
        )

    job_id = _start_job(db, item["_id"])
    job = db.ai_jobs.find_one({"_id": job_id})
    return jsonify({"success": True, "job": serialize_doc(job)}), 202


@ai_bp.route("/api/items/<item_id>/reanalyze", methods=["POST"])
def reanalyze_item_route(item_id):
    """Explicit re-analysis (section 23) - always creates a new job/version."""
    db = get_db()
    item = _find_item_or_404(db, item_id)
    job_id = _start_job(db, item["_id"], reanalyze=True)
    job = db.ai_jobs.find_one({"_id": job_id})
    return jsonify({"success": True, "job": serialize_doc(job)}), 202


@ai_bp.route("/api/items/<item_id>/analysis", methods=["GET"])
def get_item_analysis(item_id):
    db = get_db()
    item = _find_item_or_404(db, item_id)
    if not item.get("ai_analysis_id"):
        raise ApiError(
            "ANALYSIS_NOT_FOUND", "This item has not been analyzed yet.", 404
        )
    analysis = db.ai_analyses.find_one({"_id": item["ai_analysis_id"]})
    return jsonify({"success": True, "analysis": serialize_doc(analysis)})


@ai_bp.route("/api/jobs/<job_id>", methods=["GET"])
def get_job(job_id):
    db = get_db()
    oid = _object_id_or_404(job_id)
    job = db.ai_jobs.find_one({"_id": oid})
    if not job:
        raise ApiError("JOB_NOT_FOUND", f"No job found with id '{job_id}'.", 404)
    return jsonify({"success": True, "job": serialize_doc(job)})


@ai_bp.route("/api/jobs/<job_id>/retry", methods=["POST"])
def retry_job(job_id):
    """Deliberately retry a failed job with a bounded retry count."""
    db = get_db()
    oid = _object_id_or_404(job_id)
    failed_job = db.ai_jobs.find_one({"_id": oid})
    if not failed_job:
        raise ApiError("JOB_NOT_FOUND", f"No job found with id '{job_id}'.", 404)
    if failed_job.get("status") != "FAILED":
        raise ApiError(
            "JOB_NOT_RETRYABLE", "Only failed analysis jobs can be retried.", 409
        )
    retry_count = int(failed_job.get("retry_count", 0))
    if retry_count >= Config.AI_JOB_MAX_RETRIES:
        raise ApiError(
            "RETRY_LIMIT_REACHED",
            f"This job has reached the retry limit of {Config.AI_JOB_MAX_RETRIES}.",
            409,
        )
    item = db.instagram_items.find_one({"_id": failed_job["item_id"]})
    if not item:
        raise ApiError("ITEM_NOT_FOUND", "The Reel for this job was deleted.", 404)
    new_job_id = create_job(
        db,
        item["_id"],
        job_type="RETRY",
        retry_of=failed_job["_id"],
        retry_count=retry_count + 1,
    )
    db.instagram_items.update_one(
        {"_id": item["_id"]}, {"$set": {"analysis_status": "QUEUED"}}
    )
    job = db.ai_jobs.find_one({"_id": new_job_id})
    return jsonify({"success": True, "job": serialize_doc(job)}), 202


@ai_bp.route("/api/items/<item_id>/retry-analysis", methods=["POST"])
def retry_item_analysis(item_id):
    """Retry the most recent failed job for one Reel."""
    db = get_db()
    item = _find_item_or_404(db, item_id)
    failed_job = db.ai_jobs.find_one(
        {"item_id": item["_id"], "status": "FAILED"}, sort=[("completed_at", -1)]
    )
    if not failed_job:
        raise ApiError(
            "FAILED_JOB_NOT_FOUND",
            "This Reel has no failed analysis job to retry.",
            404,
        )
    retry_count = int(failed_job.get("retry_count", 0))
    if retry_count >= Config.AI_JOB_MAX_RETRIES:
        raise ApiError(
            "RETRY_LIMIT_REACHED",
            f"This job has reached the retry limit of {Config.AI_JOB_MAX_RETRIES}.",
            409,
        )
    new_job_id = create_job(
        db,
        item["_id"],
        job_type="RETRY",
        retry_of=failed_job["_id"],
        retry_count=retry_count + 1,
    )
    db.instagram_items.update_one(
        {"_id": item["_id"]}, {"$set": {"analysis_status": "QUEUED"}}
    )
    return (
        jsonify(
            {
                "success": True,
                "job": serialize_doc(db.ai_jobs.find_one({"_id": new_job_id})),
            }
        ),
        202,
    )


@ai_bp.route("/api/ai/worker/run", methods=["POST"])
def run_ai_worker():
    expected_token = current_app.config.get("SAVEDFLOW_WORKER_TOKEN", "")
    provided_token = request.headers.get("X-SavedFlow-Worker-Token", "")

    if not expected_token or provided_token != expected_token:
        raise ApiError(
            "WORKER_UNAUTHORIZED",
            "Invalid worker token.",
            401,
        )

    db = get_db()
    job = claim_next_job(db)

    if not job:
        return jsonify(
            {
                "success": True,
                "processed": False,
                "message": "No queued AI jobs.",
            }
        )

    run_analysis_job(db, job["_id"])

    updated_job = db.ai_jobs.find_one({"_id": job["_id"]})

    return jsonify(
        {
            "success": True,
            "processed": True,
            "job": serialize_doc(updated_job),
        }
    )
