"""
Consistent JSON error handling (section 31).

Every error the API returns goes through ApiError / error_response so the
shape is always:

{
    "success": false,
    "error": {"code": "...", "message": "..."}
}
"""
from flask import jsonify


class ApiError(Exception):
    """Raised anywhere in the app to produce a structured JSON error response."""

    def __init__(self, code, message, status_code=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def error_response(code, message, status_code=400):
    return jsonify({
        "success": False,
        "error": {"code": code, "message": message},
    }), status_code


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(err):
        return error_response(err.code, err.message, err.status_code)

    @app.errorhandler(404)
    def handle_404(err):
        return error_response("NOT_FOUND", "The requested resource was not found.", 404)

    @app.errorhandler(405)
    def handle_405(err):
        return error_response("METHOD_NOT_ALLOWED", "This HTTP method is not allowed for this endpoint.", 405)

    @app.errorhandler(500)
    def handle_500(err):
        return error_response("INTERNAL_ERROR", "An unexpected internal error occurred.", 500)
