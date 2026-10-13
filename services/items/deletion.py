"""Careful, single-item cleanup for SavedFlow records and GridFS files."""

from bson import ObjectId
from gridfs import GridFSBucket

from utils.dates import utcnow


def _object_id(value):
    if value in (None, ""):
        return None
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(value)
    except Exception:
        return None


def _evidence_file_ids(evidence):
    ids = [_object_id(evidence.get("video_file_id"))]
    ids.extend(_object_id(value) for value in evidence.get("frame_file_ids", []))
    return {value for value in ids if value is not None}


def _file_is_referenced_by_other_evidence(db, file_id, excluded_evidence_ids):
    return (
        db.evidence.count_documents(
            {
                "_id": {"$nin": list(excluded_evidence_ids)},
                "$or": [
                    {"video_file_id": file_id},
                    {"frame_file_ids": file_id},
                ],
            }
        )
        > 0
    )


def _file_is_referenced_by_other_item(db, file_id, item_id):
    return (
        db.instagram_items.count_documents(
            {
                "_id": {"$ne": item_id},
                "source_metadata.thumbnail_file_id": {"$in": [file_id, str(file_id)]},
            }
        )
        > 0
    )


def _delete_gridfs_files(bucket, file_ids):
    for file_id in file_ids:
        try:
            bucket.delete(file_id)
        except Exception as exc:
            # A missing file is already clean; a different GridFS failure must
            # be reported to the caller so the item record can be retained.
            if "No file" not in str(exc) and "not found" not in str(exc).lower():
                raise


def delete_item_and_related(db, item):
    """Delete one item and its exclusively owned records.

    The function identifies shared GridFS references before deleting blobs.
    It performs GridFS cleanup before removing the MongoDB metadata, so a
    storage error leaves enough information to retry deletion safely.
    """

    item_id = item["_id"]
    normalized_url = item.get("normalized_url")
    if normalized_url:
        db.deleted_items.update_one(
            {"normalized_url": normalized_url},
            {
                "$set": {
                    "normalized_url": normalized_url,
                    "instagram_media_id": item.get("instagram_media_id"),
                    "original_item_id": item_id,
                    "url": item.get("url"),
                    "deleted_at": utcnow(),
                }
            },
            upsert=True,
        )
    evidence_docs = list(db.evidence.find({"item_id": item_id}))
    evidence_ids = {doc["_id"] for doc in evidence_docs}
    analysis_count = db.ai_analyses.count_documents({"item_id": item_id})
    action_count = db.actions.count_documents({"item_id": item_id})
    job_count = db.ai_jobs.count_documents({"item_id": item_id})
    evidence_file_ids = set()
    for doc in evidence_docs:
        evidence_file_ids.update(_evidence_file_ids(doc))

    exclusive_evidence_files = {
        file_id
        for file_id in evidence_file_ids
        if not _file_is_referenced_by_other_evidence(db, file_id, evidence_ids)
    }

    thumbnail_file_id = _object_id(
        (item.get("source_metadata") or {}).get("thumbnail_file_id")
    )
    exclusive_thumbnail_files = set()
    if thumbnail_file_id and not _file_is_referenced_by_other_item(
        db, thumbnail_file_id, item_id
    ):
        exclusive_thumbnail_files.add(thumbnail_file_id)

    if exclusive_evidence_files:
        _delete_gridfs_files(
            GridFSBucket(db, bucket_name="evidence"), exclusive_evidence_files
        )
    if exclusive_thumbnail_files:
        _delete_gridfs_files(
            GridFSBucket(db, bucket_name="thumbnails"), exclusive_thumbnail_files
        )

    # Delete dependent records before the item. A worker that has already
    # claimed a job rechecks both job and item existence before it persists an
    # analysis, so it cannot create a new orphaned result after this point.
    db.ai_jobs.delete_many({"item_id": item_id})
    db.ai_analyses.delete_many({"item_id": item_id})
    db.actions.delete_many({"item_id": item_id})
    db.evidence.delete_many({"item_id": item_id})
    db.instagram_items.delete_one({"_id": item_id})

    return {
        "analyses": analysis_count,
        "actions": action_count,
        "jobs": job_count,
        "evidence": len(evidence_docs),
        "evidence_files_deleted": len(exclusive_evidence_files),
        "thumbnail_files_deleted": len(exclusive_thumbnail_files),
    }
