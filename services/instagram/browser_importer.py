"""Import sanitized discoveries produced by the local Playwright helper.

The Flask process never receives cookies, storage state, passwords, or media
bytes. This adapter only accepts Reel URLs and optional visible metadata.
"""

import re

from pymongo.errors import DuplicateKeyError

from models.item import new_item
from services.instagram.base import BaseImporter, ImportResult
from utils.urls import is_valid_instagram_url, normalize_instagram_url

MARKDOWN_URL_RE = re.compile(
    r"^(?:!\[[^\]]*\]|\[[^\]]*\])\s*\((https?://[^)\s]+)\)\s*$",
    re.IGNORECASE,
)
RAW_URL_RE = re.compile(r"https?://[^\s)\]>\"'`]+", re.IGNORECASE)


def clean_thumbnail_url(value):
    if not isinstance(value, str):
        return None

    value = value.strip()
    if not value:
        return None

    value = value.strip("'\"` ")

    match = MARKDOWN_URL_RE.match(value)

    if match:
        return match.group(1).strip()

    raw_match = RAW_URL_RE.search(value)
    if raw_match:
        return raw_match.group(0).strip()

    return value or None


class LocalBrowserImporter(BaseImporter):
    def __init__(self, db):
        self.db = db

    def run(self, entries):
        result = ImportResult()
        if not isinstance(entries, list):
            entries = []
        result.total_submitted = len(entries)
        seen = set()
        for entry in entries:
            if not isinstance(entry, dict):
                result.invalid += 1
                result.invalid_items.append(
                    {"item": entry, "reason": "Expected an object."}
                )
                continue
            url = entry.get("url")
            if not is_valid_instagram_url(url):
                result.invalid += 1
                result.invalid_items.append(
                    {"url": url, "reason": "Not a recognized Instagram URL."}
                )
                continue
            normalized = normalize_instagram_url(url)
            media_id = entry.get("instagram_media_id")
            duplicate_query = {"$or": [{"normalized_url": normalized}]}
            if media_id:
                duplicate_query["$or"].append({"instagram_media_id": media_id})
            suppression_query = {"$or": [{"normalized_url": normalized}]}
            if media_id:
                suppression_query["$or"].append({"instagram_media_id": media_id})
            if self.db.deleted_items.find_one(suppression_query):
                result.skipped_deleted += 1
                continue
            existing = self.db.instagram_items.find_one(duplicate_query)
            if normalized in seen or existing:
                # A later local sync can enrich earlier URL-only imports with
                # visible thumbnail/label metadata without making a duplicate.
                if existing:
                    metadata = dict(existing.get("source_metadata") or {})
                    for key in (
                        "thumbnail_url",
                        "thumbnail_file_id",
                        "visible_label",
                    ):
                        if entry.get(key):
                            if key == "thumbnail_url":
                                metadata[key] = clean_thumbnail_url(entry.get(key))
                            else:
                                metadata[key] = entry[key]
                    updates = {"source_metadata": metadata}
                    caption = entry.get("caption") or entry.get("visible_label")
                    if caption and not existing.get("caption"):
                        updates["caption"] = caption
                    self.db.instagram_items.update_one(
                        {"_id": existing["_id"]}, {"$set": updates}
                    )
                result.duplicates += 1
                continue
            seen.add(normalized)
            item = new_item(
                url=url.strip(),
                normalized_url=normalized,
                source_method="LOCAL_BROWSER",
                instagram_media_id=media_id,
                creator_username=entry.get("creator_username"),
                caption=entry.get("caption") or entry.get("visible_label"),
                media_type=entry.get("media_type", "VIDEO"),
                media_status="UNKNOWN",
                saved_at=entry.get("saved_at"),
                source_metadata={
                    "discovered_by": "local_playwright",
                    "collection": "saved",
                    "thumbnail_url": clean_thumbnail_url(entry.get("thumbnail_url")),
                    "thumbnail_file_id": entry.get("thumbnail_file_id"),
                    "visible_label": entry.get("visible_label"),
                },
            )
            try:
                inserted = self.db.instagram_items.insert_one(item)
            except DuplicateKeyError:
                result.duplicates += 1
                continue

            result.imported += 1
            result.metadata_only += 1
            result.imported_ids.append(inserted.inserted_id)
        return result
