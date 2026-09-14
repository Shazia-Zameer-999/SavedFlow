"""Generic request-body validation helpers used across routes."""
from utils.errors import ApiError


def require_json_body(request):
    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        raise ApiError("INVALID_REQUEST_BODY", "Request body must be a JSON object.", 400)
    return data


def require_fields(data, fields):
    missing = [f for f in fields if f not in data or data[f] in (None, "")]
    if missing:
        raise ApiError(
            "MISSING_FIELDS",
            f"Missing required field(s): {', '.join(missing)}.",
            400,
        )


def parse_pagination(args):
    try:
        page = max(int(args.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(args.get("page_size", 20))
    except (TypeError, ValueError):
        page_size = 20
    page_size = max(1, min(page_size, 100))
    return page, page_size
