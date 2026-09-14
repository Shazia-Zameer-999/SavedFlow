"""
Bulk manual URL importer (section 3.3).

This is the always-available fallback import path: the user pastes a list
of Instagram URLs and SavedFlow validates, normalizes, de-duplicates, and
stores them. No URL is ever silently dropped - every one submitted is
accounted for in the returned counts.
"""
from pymongo.errors import DuplicateKeyError

from models.item import new_item
from services.instagram.base import BaseImporter, ImportResult
from utils.urls import is_valid_instagram_url, normalize_instagram_url


class ManualURLImporter(BaseImporter):
    def __init__(self, db):
        self.db = db

    def run(self, urls):
        result = ImportResult()
        if not isinstance(urls, list):
            urls = [urls]

        result.total_submitted = len(urls)
        seen_in_batch = set()

        for raw_url in urls:
            if not isinstance(raw_url, str) or not raw_url.strip():
                result.invalid += 1
                result.invalid_items.append({"url": raw_url, "reason": "Empty or non-string URL."})
                continue

            url = raw_url.strip()

            if not is_valid_instagram_url(url):
                result.invalid += 1
                result.invalid_items.append({"url": url, "reason": "Not a recognized Instagram post/reel URL."})
                continue

            normalized = normalize_instagram_url(url)

            if normalized in seen_in_batch or self.db.instagram_items.find_one({"normalized_url": normalized}):
                result.duplicates += 1
                continue

            seen_in_batch.add(normalized)

            item = new_item(url=url, normalized_url=normalized, source_method="MANUAL")
            try:
                inserted = self.db.instagram_items.insert_one(item)
                result.imported += 1
                result.imported_ids.append(inserted.inserted_id)
            except DuplicateKeyError:
                result.duplicates += 1

        return result
