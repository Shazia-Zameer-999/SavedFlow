"""
MongoDB/GridFS storage for SavedFlow evidence.

Stores:
- captured Reel video in GridFS
- representative frames in GridFS
- transcript and evidence metadata in MongoDB

This module does not call Gemini and does not create AI jobs.
"""

from pathlib import Path
from typing import Any

from bson import ObjectId
from gridfs import GridFSBucket

from utils.dates import utcnow

EVIDENCE_COLLECTION = "evidence"
GRIDFS_BUCKET_NAME = "evidence"


def _upload_file(
    bucket: GridFSBucket,
    file_path: str | Path,
    filename: str,
    metadata: dict[str, Any] | None = None,
):
    """
    Upload one local file to MongoDB GridFS and return its GridFS file ID.
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Evidence file does not exist: {file_path}")

    upload_stream = bucket.open_upload_stream(
        filename,
        metadata=metadata or {},
    )
    try:
        with file_path.open("rb") as file_handle:
            while chunk := file_handle.read(1024 * 1024):
                upload_stream.write(chunk)
    finally:
        upload_stream.close()
    return upload_stream._id


def store_evidence(
    db,
    evidence: dict[str, Any],
    item_id=None,
    source_url: str | None = None,
):
    """
    Store one complete evidence package in MongoDB/GridFS.

    Returns the inserted evidence document.
    """

    bucket = GridFSBucket(
        db,
        bucket_name=GRIDFS_BUCKET_NAME,
    )

    video_path = Path(evidence["video_path"])
    duration = evidence.get("duration")
    transcript = evidence.get("transcript", "")
    transcript_source = evidence.get("transcript_source")
    frame_paths = evidence.get("frames", [])

    video_file_id = _upload_file(
        bucket=bucket,
        file_path=video_path,
        filename=video_path.name,
        metadata={
            "evidence_type": "VIDEO",
            "source_url": source_url,
        },
    )

    frame_file_ids = []

    for index, frame_path in enumerate(frame_paths, start=1):
        frame_path = Path(frame_path)

        frame_file_id = _upload_file(
            bucket=bucket,
            file_path=frame_path,
            filename=frame_path.name,
            metadata={
                "evidence_type": "FRAME",
                "frame_number": index,
                "source_url": source_url,
            },
        )

        frame_file_ids.append(frame_file_id)

    evidence_doc = {
        "item_id": item_id,
        "source_url": source_url,
        "video_file_id": video_file_id,
        "frame_file_ids": frame_file_ids,
        "duration": duration,
        "frame_count": len(frame_file_ids),
        "transcript": transcript,
        "transcript_source": transcript_source,
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }

    inserted = db[EVIDENCE_COLLECTION].insert_one(evidence_doc)

    evidence_doc["_id"] = inserted.inserted_id

    return evidence_doc


def get_evidence(db, evidence_id):
    """
    Retrieve an evidence metadata document by ID.
    """
    if not isinstance(evidence_id, ObjectId):
        evidence_id = ObjectId(evidence_id)

    return db[EVIDENCE_COLLECTION].find_one({"_id": evidence_id})


def get_evidence_for_item(db, item_id):
    """
    Retrieve the latest evidence package for one SavedFlow item.
    """
    return db[EVIDENCE_COLLECTION].find_one(
        {"item_id": item_id},
        sort=[("created_at", -1)],
    )


def download_evidence_video(db, evidence, output_path):
    """
    Download the stored evidence video from GridFS
    to a local temporary file.

    Returns the local file path.
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

    download_stream = bucket.open_download_stream(evidence["video_file_id"])
    with output_path.open("wb") as file_handle:
        while chunk := download_stream.read(1024 * 1024):
            file_handle.write(chunk)

    return str(output_path)


def download_evidence_frames(db, evidence, output_dir):
    """Download stored representative frames for one temporary AI request."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    bucket = GridFSBucket(db, bucket_name=GRIDFS_BUCKET_NAME)
    paths = []
    for index, file_id in enumerate(evidence.get("frame_file_ids", []), start=1):
        output_path = output_dir / f"frame-{index}.jpg"
        download_stream = bucket.open_download_stream(file_id)
        with output_path.open("wb") as file_handle:
            while chunk := download_stream.read(1024 * 1024):
                file_handle.write(chunk)
        paths.append(str(output_path))
    return paths
