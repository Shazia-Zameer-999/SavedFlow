"""GET /api/health (section 30)."""
from flask import Blueprint, jsonify

from config import Config
from extensions import check_connection, is_using_mock

health_bp = Blueprint("health", __name__)


@health_bp.route("/api/health", methods=["GET"])
def health():
    db_connected = is_using_mock() or check_connection()
    return jsonify({
        "status": "ok" if db_connected else "degraded",
        "database": "connected" if db_connected else "disconnected",
        "ai_configured": Config.ai_configured(),
        "instagram_configured": Config.instagram_configured(),
    })
