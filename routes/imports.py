"""
Import API (sections 3, 27).

All three import methods funnel through here. The official-API route is
honest about the platform limitation described in
services/instagram/api_importer.py rather than faking synchronization.
"""
from flask import Blueprint, jsonify, request

from config import Config
from extensions import get_db
from services.instagram.api_importer import InstagramAPIImporter
from services.instagram.export_importer import InstagramExportImporter
from services.instagram.manual_importer import ManualURLImporter
from services.instagram.browser_importer import LocalBrowserImporter
from utils.errors import ApiError
from utils.validation import require_json_body

imports_bp = Blueprint("imports", __name__)


@imports_bp.route("/api/import/manual", methods=["POST"])
def import_manual():
    db = get_db()
    data = require_json_body(request)
    urls = data.get("urls")
    if urls is None:
        raise ApiError("MISSING_FIELDS", "Missing required field: urls (a list of Instagram URLs).", 400)

    importer = ManualURLImporter(db)
    result = importer.run(urls)
    return jsonify({"success": True, **result.to_dict()})


@imports_bp.route("/api/import/export", methods=["POST"])
def import_export():
    """
    Accepts a parsed Instagram data-export JSON body (section 3.2). If the
    user has a raw export .json file, they should send its parsed content
    as the request body.
    """
    db = get_db()
    export_data = request.get_json(silent=True)
    if export_data is None:
        raise ApiError("INVALID_EXPORT", "Request body must contain the parsed Instagram export JSON.", 400)

    importer = InstagramExportImporter(db)
    outcome = importer.run(export_data)
    return jsonify({"success": True, **outcome})


@imports_bp.route("/api/import/instagram", methods=["POST"])
def import_instagram_api():
    """
    Official Meta API import (section 3.1). Honestly reports that saved-
    collection sync is unavailable (section 2) rather than faking it.
    """
    db = get_db()
    importer = InstagramAPIImporter(
        db,
        access_token=Config.META_ACCESS_TOKEN,
        ig_account_id=Config.INSTAGRAM_ACCOUNT_ID,
    )
    status = importer.get_saved_content_status()
    return jsonify(status), 200


@imports_bp.route("/api/instagram/sync", methods=["POST"])
def sync_instagram_saved():
    """Accept discoveries from the user-run local browser helper only."""
    data = require_json_body(request)
    if data.get("source") != "local_playwright":
        raise ApiError("INVALID_SYNC_SOURCE", "Only the local Playwright discovery source is accepted.", 400)
    if data.get("status") in {"AUTH_REQUIRED", "LOGIN_CHALLENGE", "BROWSER_UNAVAILABLE"}:
        return jsonify({"success": False, "status": data["status"], "imported": 0}), 401
    db = get_db()
    result = LocalBrowserImporter(db).run(data.get("items", []))
    return jsonify({"success": True, "status": "COMPLETED", **result.to_dict()})


@imports_bp.route("/api/import/status", methods=["GET"])
def import_status():
    db = get_db()
    counts = {
        "MANUAL": db.instagram_items.count_documents({"source_method": "MANUAL"}),
        "EXPORT": db.instagram_items.count_documents({"source_method": "EXPORT"}),
        "API": db.instagram_items.count_documents({"source_method": "API"}),
        "LOCAL_BROWSER": db.instagram_items.count_documents({"source_method": "LOCAL_BROWSER"}),
    }
    return jsonify({
        "success": True,
        "total_items": sum(counts.values()),
        "by_source_method": counts,
        "instagram_api_saved_content_available": False,
        "instagram_configured": Config.instagram_configured(),
    })
