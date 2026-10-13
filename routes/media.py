"""Read-only media endpoints for files already stored in GridFS."""

from io import BytesIO

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, send_file
from gridfs import GridFSBucket
from gridfs.errors import NoFile

from extensions import get_db
from utils.errors import ApiError

media_bp = Blueprint("media", __name__)


@media_bp.route("/api/thumbnails/<file_id>", methods=["GET"])
def get_thumbnail(file_id):
    try:
        object_id = ObjectId(file_id)
    except (InvalidId, TypeError):
        raise ApiError("THUMBNAIL_NOT_FOUND", "Thumbnail not found.", 404)

    bucket = GridFSBucket(get_db(), bucket_name="thumbnails")

    try:
        grid_file = bucket.open_download_stream(object_id)
        content = grid_file.read()
        metadata = grid_file.metadata or {}
    except NoFile:
        raise ApiError("THUMBNAIL_NOT_FOUND", "Thumbnail not found.", 404)

    content_type = metadata.get("content_type") or "image/jpeg"
    if not content_type.startswith("image/"):
        content_type = "application/octet-stream"

    return send_file(
        BytesIO(content),
        mimetype=content_type,
        download_name="thumbnail",
        max_age=3600,
    )
