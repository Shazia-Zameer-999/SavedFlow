"""
AI analysis + job endpoints (sections 22-23).

POST /api/items/<id>/analyze creates a job and either runs it inline
(TESTING/no background thread desired) or kicks off a background thread,
then returns the job immediately (202) so the HTTP request never blocks
on the AI call.
"""
from flask import Blueprint, current_app, jsonify, request

from extensions import get_db
from models.job import JOB_STATUSES
from routes.items import _find_item_or_404, _object_id_or_404
from services.jobs.manager import create_job, run_analysis_job, start_analysis_job_async
from utils.errors import ApiError
from utils.json_utils import serialize_doc

ai_bp = Blueprint("ai", __name__)


def _start_job(db, item_id_oid, reanalyze=False):
    db.instagram_items.update_one({"_id": item_id_oid}, {"$set": {"analysis_status": "QUEUED"}})
    job_id = create_job(db, item_id_oid, job_type="REANALYZE" if reanalyze else "ANALYZE")
    if current_app.config.get("TESTING"):
        # Deterministic, synchronous execution in tests.
        run_analysis_job(db, job_id)
    else:
        start_analysis_job_async(db, job_id)
    return job_id


@ai_bp.route("/api/items/<item_id>/analyze", methods=["POST"])
def analyze_item_route(item_id):
    db = get_db()
    item = _find_item_or_404(db, item_id)


    if item.get("analysis_status") == "COMPLETED":
        return jsonify({
            "success": True,
            "message": "Item already analyzed. Use /reanalyze to force a new analysis.",
            "item": serialize_doc(item),
        })

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
        raise ApiError("ANALYSIS_NOT_FOUND", "This item has not been analyzed yet.", 404)
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
