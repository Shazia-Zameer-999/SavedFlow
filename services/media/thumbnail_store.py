from pathlib import Path

from gridfs import GridFSBucket

GRIDFS_BUCKET_NAME = "thumbnails"


def store_thumbnail(db, image_path, item_id=None, source_url=None):
    """
    Store an Instagram thumbnail in MongoDB GridFS.

    Returns the GridFS file ID.
    """

    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(f"Thumbnail file does not exist: {image_path}")

    bucket = GridFSBucket(
        db,
        bucket_name=GRIDFS_BUCKET_NAME,
    )

    metadata = {
        "item_id": item_id,
        "source_url": source_url,
        "content_type": "image/jpeg",
    }

    upload_stream = bucket.open_upload_stream(
        image_path.name,
        metadata=metadata,
    )
    try:
        with image_path.open("rb") as file_handle:
            while chunk := file_handle.read(1024 * 1024):
                upload_stream.write(chunk)
    finally:
        upload_stream.close()

    file_id = upload_stream._id

    return file_id


def download_thumbnail(db, file_id, output_path):
    """
    Download a stored thumbnail from GridFS.
    """

    output_path = Path(output_path)
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    bucket = GridFSBucket(
        db,
        bucket_name=GRIDFS_BUCKET_NAME,
    )

    with output_path.open("wb") as file_handle:
        bucket.download_to_stream(
            file_id,
            file_handle,
        )

    return str(output_path)
