"""
Import API.

Instagram Saved synchronization is split into two parts:

1. The website creates a sync request.
2. The local Playwright helper picks up that request and performs
   discovery on the user's computer.

Instagram authentication therefore never needs to reach the Flask server.
"""
import json
from urllib.request import Request, urlopen
from datetime import datetime, timezone
from bson import ObjectId
from flask import Blueprint, jsonify, request, current_app

from config import Config
from extensions import get_db
from services.instagram.api_importer import InstagramAPIImporter
from services.instagram.export_importer import InstagramExportImporter
from services.instagram.manual_importer import ManualURLImporter
from services.instagram.browser_importer import LocalBrowserImporter
from utils.errors import ApiError
from utils.validation import require_json_body


imports_bp = Blueprint("imports", __name__)


def _utcnow():
    return datetime.now(timezone.utc)


def _object_id(value):
    try:
        return ObjectId(value)
    except Exception:
        raise ApiError(
            "INVALID_SYNC_JOB_ID",
            "Invalid sync job id.",
            400,
        )

def _trigger_github_sync():
    token = current_app.config.get("GITHUB_ACTIONS_TOKEN")

    if not token:
        raise ApiError(
            "GITHUB_ACTIONS_NOT_CONFIGURED",
            "GITHUB_ACTIONS_TOKEN is not configured.",
            503,
        )

    url = (
        "https://api.github.com/repos/"
        "Shazia-Zameer-999/SavedFlow/"
        "actions/workflows/instagram-sync.yml/dispatches"
    )

    payload = json.dumps({
        "ref": "main",
    }).encode("utf-8")

    req = Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SavedFlow",
        },
    )

    with urlopen(req, timeout=15):
        pass

def _require_sync_token():
    expected = current_app.config["SAVEDFLOW_SYNC_TOKEN"]

    if not expected:
        raise ApiError(
            "SYNC_TOKEN_NOT_CONFIGURED",
            "SAVEDFLOW_SYNC_TOKEN is not configured.",
            503,
        )

    provided = request.headers.get("X-SavedFlow-Sync-Token", "")

    if not provided or provided != expected:
        raise ApiError(
            "INVALID_SYNC_TOKEN",
            "Invalid sync agent token.",
            401,
        )


@imports_bp.route("/api/import/manual", methods=["POST"])
def import_manual():
    db = get_db()
    data = require_json_body(request)

    urls = data.get("urls")

    if urls is None:
        raise ApiError(
            "MISSING_FIELDS",
            "Missing required field: urls (a list of Instagram URLs).",
            400,
        )

    importer = ManualURLImporter(db)
    result = importer.run(urls)

    return jsonify({
        "success": True,
        **result.to_dict(),
    })


@imports_bp.route("/api/import/export", methods=["POST"])
def import_export():
    db = get_db()

    export_data = request.get_json(silent=True)

    if export_data is None:
        raise ApiError(
            "INVALID_EXPORT",
            "Request body must contain the parsed Instagram export JSON.",
            400,
        )

    importer = InstagramExportImporter(db)
    outcome = importer.run(export_data)

    return jsonify({
        "success": True,
        **outcome,
    })


@imports_bp.route("/api/import/instagram", methods=["POST"])
def import_instagram_api():
    db = get_db()

    importer = InstagramAPIImporter(
        db,
        access_token=Config.META_ACCESS_TOKEN,
        ig_account_id=Config.INSTAGRAM_ACCOUNT_ID,
    )

    status = importer.get_saved_content_status()

    return jsonify(status), 200


# ---------------------------------------------------------------------------
# Local Instagram Saved synchronization
# ---------------------------------------------------------------------------

@imports_bp.route("/api/instagram/sync/request", methods=["POST"])
def request_instagram_sync():
    """
    Create a synchronization request.

    The frontend calls this endpoint when the user presses
    "Sync Instagram Saved".

    The local Playwright helper later discovers this request.
    """

    db = get_db()

    existing = db.sync_jobs.find_one(
        {
            "status": {
                "$in": ["QUEUED", "RUNNING"],
            }
        }
    )

    if existing:
        return jsonify({
            "success": True,
            "already_running": True,
            "job_id": str(existing["_id"]),
            "status": existing["status"],
        })

    now = _utcnow()

    job = {
        "type": "INSTAGRAM_SAVED_SYNC",
        "status": "QUEUED",
        "collection_url": Config.INSTAGRAM_SAVED_URL,
        "created_at": now,
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
    }

    inserted = db.sync_jobs.insert_one(job)
    try:
        _trigger_github_sync()
    except Exception as exc:
        db.sync_jobs.update_one(
            {"_id": inserted.inserted_id},
            {
                "$set": {
                    "status": "FAILED",
                    "completed_at": _utcnow(),
                    "error": str(exc),
                }
            },
        )

        raise ApiError(
            "GITHUB_SYNC_TRIGGER_FAILED",
            "Could not start the Instagram sync workflow.",
            502,
        )

    return jsonify({
        "success": True,
        "already_running": False,
        "job_id": str(inserted.inserted_id),
        "status": "QUEUED",
    }), 202


@imports_bp.route("/api/instagram/sync/pending", methods=["GET"])
def get_pending_instagram_sync():
    """
    Called by the local sync helper.

    Only the helper possessing SAVEDFLOW_SYNC_TOKEN can claim a job.
    """

    _require_sync_token()

    db = get_db()

    job = db.sync_jobs.find_one_and_update(
        {
            "type": "INSTAGRAM_SAVED_SYNC",
            "status": "QUEUED",
        },
        {
            "$set": {
                "status": "RUNNING",
                "started_at": _utcnow(),
            }
        },
        sort=[("created_at", 1)],
    )

    if not job:
        return jsonify({
            "success": True,
            "pending": False,
        })

    return jsonify({
        "success": True,
        "pending": True,
        "job_id": str(job["_id"]),
        "collection_url": job.get("collection_url") or Config.INSTAGRAM_SAVED_URL,
    })


@imports_bp.route(
    "/api/instagram/sync/<job_id>/complete",
    methods=["POST"],
)
def complete_instagram_sync(job_id):
    """
    Mark a previously claimed sync request as completed or failed.
    """

    _require_sync_token()

    db = get_db()
    data = require_json_body(request)

    oid = _object_id(job_id)

    status = data.get("status", "COMPLETED")

    if status not in {
        "COMPLETED",
        "FAILED",
        "AUTH_REQUIRED",
        "LOGIN_CHALLENGE",
        "BROWSER_UNAVAILABLE",
    }:
        raise ApiError(
            "INVALID_SYNC_STATUS",
            "Invalid sync completion status.",
            400,
        )

    update = {
        "status": status,
        "completed_at": _utcnow(),
        "result": data.get("result"),
        "error": data.get("error"),
    }

    result = db.sync_jobs.update_one(
        {
            "_id": oid,
            "status": "RUNNING",
        },
        {
            "$set": update,
        },
    )

    if result.matched_count == 0:
        raise ApiError(
            "SYNC_JOB_NOT_FOUND",
            "The sync job was not found or is no longer running.",
            404,
        )

    return jsonify({
        "success": True,
        "job_id": job_id,
        "status": status,
    })


@imports_bp.route("/api/instagram/sync", methods=["POST"])
def sync_instagram_saved():
    """
    Receive discovered Instagram Saved items from the local Playwright
    helper.
    """

    _require_sync_token()

    data = require_json_body(request)

    if data.get("source") != "local_playwright":
        raise ApiError(
            "INVALID_SYNC_SOURCE",
            "Only the local Playwright discovery source is accepted.",
            400,
        )

    if data.get("status") in {
        "AUTH_REQUIRED",
        "LOGIN_CHALLENGE",
        "BROWSER_UNAVAILABLE",
    }:
        return jsonify({
            "success": False,
            "status": data["status"],
            "imported": 0,
        }), 401

    db = get_db()

    result = LocalBrowserImporter(db).run(
        data.get("items", [])
    )

    return jsonify({
        "success": True,
        "status": "COMPLETED",
        **result.to_dict(),
    })


@imports_bp.route("/api/import/status", methods=["GET"])
def import_status():
    db = get_db()

    counts = {
        "MANUAL": db.instagram_items.count_documents(
            {"source_method": "MANUAL"}
        ),
        "EXPORT": db.instagram_items.count_documents(
            {"source_method": "EXPORT"}
        ),
        "API": db.instagram_items.count_documents(
            {"source_method": "API"}
        ),
        "LOCAL_BROWSER": db.instagram_items.count_documents(
            {"source_method": "LOCAL_BROWSER"}
        ),
    }

    active_sync = db.sync_jobs.find_one(
        {
            "type": "INSTAGRAM_SAVED_SYNC",
            "status": {
                "$in": ["QUEUED", "RUNNING"],
            },
        },
        sort=[("created_at", -1)],
    )

    return jsonify({
        "success": True,
        "total_items": sum(counts.values()),
        "by_source_method": counts,
        "instagram_api_saved_content_available": False,
        "instagram_configured": Config.instagram_configured(),
        "sync": {
            "configured": bool(Config.SAVEDFLOW_SYNC_TOKEN),
            "collection_url": Config.INSTAGRAM_SAVED_URL,
            "status": active_sync["status"] if active_sync else "IDLE",
            "job_id": str(active_sync["_id"]) if active_sync else None,
        },
    })