"""
Durable AI analysis job manager.

Jobs are tracked in MongoDB so their status can be polled independently
of the process that executes them.
"""

import os
import shutil
import tempfile
from datetime import timedelta

from pymongo import ReturnDocument

from config import Config
from models.job import new_job
from services.ai.analyzer import analyze_item, AnalysisValidationError
from services.ai.client import AIClient, AIClientError, GeminiQuotaError
from models.analysis import new_analysis
from services.media.evidence_store import (
    get_evidence_for_item,
    download_evidence_video,
    download_evidence_frames,
)
from services.media.capture import EvidenceCaptureError, capture_and_store_evidence
from services.ai.usage import GeminiDailyLimitExceeded, reserve_gemini_request
from utils.dates import utcnow


def create_job(db, item_id, job_type="ANALYZE", retry_of=None, retry_count=0):
    """Create one queued job per item while an analysis is already pending."""
    _requeue_stale_jobs(db)
    existing = db.ai_jobs.find_one(
        {
            "item_id": item_id,
            "status": {
                "$in": ["QUEUED", "WAITING_FOR_QUOTA", "RETRY_WAIT", "PROCESSING"]
            },
        }
    )
    if existing:
        return existing["_id"]
    job = new_job(
        item_id,
        job_type=job_type,
        retry_of=retry_of,
        retry_count=retry_count,
    )
    inserted = db.ai_jobs.insert_one(job)
    return inserted.inserted_id


def _requeue_stale_jobs(db):
    stale_deadline = utcnow() - timedelta(seconds=Config.AI_JOB_STALE_TIMEOUT_SECONDS)
    stale_jobs = list(
        db.ai_jobs.find(
            {
                "status": "PROCESSING",
                "$or": [
                    {"started_at": {"$lt": stale_deadline}},
                    {"started_at": None, "created_at": {"$lt": stale_deadline}},
                ],
            }
        )
    )

    for stale_job in stale_jobs:
        db.ai_jobs.update_one(
            {"_id": stale_job["_id"], "status": "PROCESSING"},
            {
                "$set": {
                    "status": "QUEUED",
                    "stage": "QUEUED",
                    "error": None,
                    "started_at": None,
                }
            },
        )
        if stale_job.get("item_id"):
            db.instagram_items.update_one(
                {"_id": stale_job["item_id"]},
                {"$set": {"analysis_status": "QUEUED", "updated_at": utcnow()}},
            )


def claim_next_job(db):
    """Atomically claim the oldest queued job; safe across worker processes."""
    _requeue_stale_jobs(db)

    now = utcnow()
    return db.ai_jobs.find_one_and_update(
        {
            "status": {"$in": ["QUEUED", "WAITING_FOR_QUOTA", "RETRY_WAIT"]},
            "$or": [
                {"retry_after": {"$exists": False}},
                {"retry_after": None},
                {"retry_after": {"$lte": now}},
            ],
        },
        {
            "$set": {
                "status": "PROCESSING",
                "stage": "PREPARING",
                "started_at": utcnow(),
                "error": None,
            },
            "$inc": {"attempt_count": 1},
        },
        sort=[("created_at", 1)],
        return_document=ReturnDocument.AFTER,
    )


def _set_stage(db, job_id, stage):
    db.ai_jobs.update_one(
        {"_id": job_id, "status": "PROCESSING"},
        {"$set": {"stage": stage}},
    )


def _fail_job(db, job_id, item_id, error):
    db.ai_jobs.update_one(
        {"_id": job_id},
        {
            "$set": {
                "status": "FAILED",
                "stage": "FAILED",
                "error": str(error),
                "completed_at": utcnow(),
            }
        },
    )
    db.instagram_items.update_one(
        {"_id": item_id},
        {"$set": {"analysis_status": "FAILED", "updated_at": utcnow()}},
    )


def _defer_for_quota(db, job_id, item_id, error, retry_after):
    now = utcnow()
    db.ai_jobs.update_one(
        {"_id": job_id, "status": "PROCESSING"},
        {
            "$set": {
                "status": "WAITING_FOR_QUOTA",
                "stage": "WAITING_FOR_GEMINI_QUOTA",
                "error": str(error),
                "retry_after": retry_after,
                "started_at": None,
            }
        },
    )
    db.instagram_items.update_one(
        {"_id": item_id},
        {"$set": {"analysis_status": "WAITING_FOR_QUOTA", "updated_at": now}},
    )


def run_analysis_job(db, job_id, ai_client=None):
    """
    Synchronously execute an ANALYZE job.

    If stored evidence exists for the item, reuse its stored video
    and transcript instead of regenerating evidence.

    The stored video is temporarily downloaded from GridFS and
    deleted after analysis.
    """

    job = db.ai_jobs.find_one({"_id": job_id, "status": "PROCESSING"})

    if not job:
        return

    item = db.instagram_items.find_one({"_id": job["item_id"]})

    if not item:
        _fail_job(db, job_id, job["item_id"], "Item no longer exists.")
        return

    db.instagram_items.update_one(
        {"_id": item["_id"]},
        {"$set": {"analysis_status": "PROCESSING", "updated_at": utcnow()}},
    )

    temporary_video_path = None
    temporary_evidence_dir = None

    try:
        item_for_analysis = dict(item)

        # ---------------------------------------------------------
        # Reuse previously captured evidence from GridFS.
        # ---------------------------------------------------------

        evidence = get_evidence_for_item(db, item["_id"])

        # Evidence capture is only attempted for this explicitly requested
        # job, only when a local browser profile has been configured, and is
        # skipped when reusable evidence is already stored.
        if not evidence and Config.INSTAGRAM_BROWSER_PROFILE:
            evidence = capture_and_store_evidence(
                db,
                item,
                on_stage=lambda stage: _set_stage(db, job_id, stage),
            )

        if evidence:
            # Reuse the transcript that was already generated
            # during evidence capture.
            if evidence.get("transcript"):
                item_for_analysis["transcript"] = evidence["transcript"]

            if evidence.get("transcript_source"):
                item_for_analysis["transcript_source"] = evidence["transcript_source"]

        if evidence and evidence.get("video_file_id"):
            _set_stage(db, job_id, "LOADING_STORED_EVIDENCE")
            temporary_evidence_dir = tempfile.mkdtemp(prefix="savedflow-evidence-")
            temporary_video_path = os.path.join(temporary_evidence_dir, "reel.webm")

            download_evidence_video(
                db,
                evidence,
                temporary_video_path,
            )

            item_for_analysis["local_video_path"] = temporary_video_path
            item_for_analysis["evidence_frame_paths"] = download_evidence_frames(
                db,
                evidence,
                os.path.join(temporary_evidence_dir, "frames"),
            )

        # ---------------------------------------------------------
        # Run AI analysis.
        #
        # Passing the stored evidence prevents analyzer.py from
        # regenerating the transcript/frames.
        # ---------------------------------------------------------

        client = ai_client or AIClient()

        if client.is_configured():
            try:
                reserve_gemini_request(db)
            except GeminiDailyLimitExceeded as exc:
                retry_after = (utcnow() + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                _defer_for_quota(db, job_id, item["_id"], exc, retry_after)
                return

        analysis_evidence = None

        if evidence:
            analysis_evidence = {
                "video_path": temporary_video_path,
                "duration": evidence.get("duration"),
                "frames": item_for_analysis.get("evidence_frame_paths", []),
                "transcript": evidence.get("transcript", ""),
                "transcript_source": evidence.get("transcript_source"),
            }

        _set_stage(db, job_id, "ANALYZING_WITH_GEMINI")
        basis, structured_output = analyze_item(
            item_for_analysis,
            ai_client=client,
            evidence=analysis_evidence,
        )

    except GeminiQuotaError as exc:
        retry_after = utcnow() + timedelta(
            seconds=Config.GEMINI_MIN_RETRY_DELAY_SECONDS
        )
        _defer_for_quota(db, job_id, item["_id"], exc, retry_after)
        return

    except (AIClientError, AnalysisValidationError, EvidenceCaptureError) as exc:
        _fail_job(db, job_id, item["_id"], exc)
        return

    except Exception as exc:  # noqa: BLE001
        _fail_job(db, job_id, item["_id"], f"Unexpected error: {exc}")
        return

    finally:
        if temporary_video_path:
            try:
                os.remove(temporary_video_path)
            except FileNotFoundError:
                pass
        if temporary_evidence_dir:
            shutil.rmtree(temporary_evidence_dir, ignore_errors=True)

    # A delete request can remove a queued/processing job while a worker is
    # calling Gemini. Recheck both documents before storing any result so a
    # deleted Reel never gains an orphaned analysis.
    still_processing = db.ai_jobs.find_one({"_id": job_id, "status": "PROCESSING"})
    item_still_exists = db.instagram_items.find_one({"_id": item["_id"]})
    if not still_processing or not item_still_exists:
        return

    existing_version = 1

    previous = db.ai_analyses.find_one(
        {"item_id": item["_id"]},
        sort=[("analysis_version", -1)],
    )

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
        {
            "$set": {
                "ai_analysis_id": inserted_analysis.inserted_id,
                "analysis_status": "COMPLETED",
                "usefulness_score": structured_output.get("overall_usefulness_score"),
                "development_relevance_score": structured_output.get(
                    "development_relevance_score"
                ),
                "implementation_value_score": structured_output.get(
                    "implementation_value_score"
                ),
                "learning_value_score": structured_output.get("learning_value_score"),
                "recommendation": structured_output.get("recommendation"),
                "technical_topic": structured_output.get("technical_topic"),
                "updated_at": utcnow(),
            }
        },
    )

    db.ai_jobs.update_one(
        {"_id": job_id},
        {
            "$set": {
                "status": "COMPLETED",
                "stage": "COMPLETED",
                "completed_at": utcnow(),
            }
        },
    )
