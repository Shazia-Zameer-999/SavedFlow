"""
Instagram data-export importer (section 3.2).

Instagram's "Download Your Information" export format has changed shape
over time, and its actual field names have varied across accounts and
export versions. Rather than assume one fixed layout, this importer looks
for a handful of known field name variants and reports exactly what it
could and couldn't find - it never guesses at data that isn't present.

Known export shapes we look for (any one item may look like):

    {"title": "...", "string_map_data": {"Href": {"value": "https://instagram.com/reel/..."}}}
    {"href": "...", "timestamp": 169..., "title": "..."}

If the export JSON doesn't contain anything recognizable as saved-content
data, `run()` returns a result with total_submitted == 0 and a
`format_supported: False` note rather than pretending to import nothing
successfully for silent reasons.
"""
from pymongo.errors import DuplicateKeyError

from models.item import new_item
from services.instagram.base import BaseImporter, ImportResult
from utils.urls import is_valid_instagram_url, normalize_instagram_url


class UnsupportedExportFormatError(Exception):
    pass


def _extract_candidate_entries(export_data):
    """
    Walk the export JSON looking for saved-item-like entries.
    Returns a list of raw dicts, each hopefully containing a URL/href and
    optional title/timestamp. Never raises on unexpected shapes - just
    returns what it could confidently find.
    """
    entries = []

    def walk(node):
        if isinstance(node, dict):
            # Common Instagram export shape: {"title": ..., "string_map_data": {...}}
            if "string_map_data" in node and isinstance(node["string_map_data"], dict):
                entries.append(node)
                return
            # Flat shape: {"href": "...", ...}
            if "href" in node:
                entries.append(node)
                return
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(export_data)
    return entries


def _get_href(entry):
    if "href" in entry and isinstance(entry["href"], str):
        return entry["href"]
    smd = entry.get("string_map_data", {})
    for key in ("Href", "href", "Link", "URL"):
        if key in smd and isinstance(smd[key], dict) and "value" in smd[key]:
            return smd[key]["value"]
    return None


def _get_caption_or_title(entry):
    if isinstance(entry.get("title"), str):
        return entry["title"]
    smd = entry.get("string_map_data", {})
    for key in ("Caption", "caption", "Title"):
        if key in smd and isinstance(smd[key], dict):
            return smd[key].get("value")
    return None


def _get_timestamp(entry):
    if "timestamp" in entry:
        return entry["timestamp"]
    smd = entry.get("string_map_data", {})
    for key in ("Time", "time", "Timestamp"):
        if key in smd and isinstance(smd[key], dict):
            return smd[key].get("timestamp")
    return None


class InstagramExportImporter(BaseImporter):
    """
    Parses a legitimate Instagram "Download Your Information" export
    (already provided by the user as parsed JSON) and imports any
    saved-content entries found in it.
    """

    def __init__(self, db):
        self.db = db

    def run(self, export_data):
        result = ImportResult()

        try:
            candidates = _extract_candidate_entries(export_data)
        except Exception:
            # A parser bug must never crash the whole application (section 3.2).
            return {
                "format_supported": False,
                "reason": "The export could not be parsed as JSON with a recognizable structure.",
                "result": result.to_dict(),
            }

        if not candidates:
            return {
                "format_supported": False,
                "reason": "No saved-content entries were found in this export. "
                          "SavedFlow currently looks for Instagram's "
                          "'string_map_data'/'href' export shapes; this file may use a "
                          "different export format or may not contain saved-content data.",
                "result": result.to_dict(),
            }

        urls = []
        extra_by_url = {}
        for entry in candidates:
            href = _get_href(entry)
            if not href:
                continue
            urls.append(href)
            extra_by_url[href] = {
                "caption": _get_caption_or_title(entry),
                "saved_at": _get_timestamp(entry),
            }

        result.total_submitted = len(urls)
        seen_in_batch = set()

        for url in urls:
            if not is_valid_instagram_url(url):
                result.invalid += 1
                result.invalid_items.append({"url": url, "reason": "Not a recognized Instagram post/reel URL."})
                continue

            normalized = normalize_instagram_url(url)
            if normalized in seen_in_batch or self.db.instagram_items.find_one({"normalized_url": normalized}):
                result.duplicates += 1
                continue
            seen_in_batch.add(normalized)

            extra = extra_by_url.get(url, {})
            item = new_item(
                url=url,
                normalized_url=normalized,
                source_method="EXPORT",
                caption=extra.get("caption"),
                saved_at=extra.get("saved_at"),
            )
            try:
                inserted = self.db.instagram_items.insert_one(item)
                result.imported += 1
                result.imported_ids.append(inserted.inserted_id)
            except DuplicateKeyError:
                result.duplicates += 1

        return {
            "format_supported": True,
            "reason": None,
            "result": result.to_dict(),
        }
