"""
Official Meta/Instagram Graph API importer (sections 2 and 3.1).

IMPORTANT, READ BEFORE CHANGING THIS FILE:

As of this project's implementation, Meta's official Instagram Graph API /
Instagram API with Instagram Login exposes a business/creator account's own
published media (via endpoints like `/{ig-user-id}/media`) and basic
account info - it does NOT expose a personal user's private "Saved"
collection. There is no supported `/me/saved` or `/saved` endpoint for
third-party apps. This is a genuine platform limitation, not a bug in this
importer, so this file must never invent such an endpoint or pretend to
call one.

Given that, this importer:
  1. Reports plainly that saved-collection sync is unavailable through the
     official API, so the rest of the app never assumes it works.
  2. Still implements a legitimate, narrower use of the official API: if
     the user has a connected business/creator IG account, it can fetch
     *that account's own published media* via `/{ig-user-id}/media`, which
     is genuinely supported and can be useful for tagging your own content
     mentions. This is optional and separate from "importing Saved posts".

If Meta ever adds official support for reading a user's Saved collection,
this is the file to update - and only after re-checking Meta's current
developer documentation for the actual endpoint and required permissions.
"""
import requests

from services.instagram.base import BaseImporter, ImportResult

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


class InstagramAPIImporter(BaseImporter):
    def __init__(self, db, access_token=None, ig_account_id=None):
        self.db = db
        self.access_token = access_token
        self.ig_account_id = ig_account_id

    def saved_content_available(self):
        """
        Always False for now - see module docstring. This is a method (not
        a hardcoded constant read elsewhere) so the honest-limitation
        response is generated in exactly one place.
        """
        return False

    def get_saved_content_status(self):
        return {
            "success": False,
            "available": False,
            "reason": (
                "Instagram's official API does not expose the user's private "
                "Saved collection. There is no supported endpoint for a "
                "third-party app to read a user's saved posts/reels. Use the "
                "Instagram data export importer or manual URL import instead."
            ),
        }

    def run(self, *args, **kwargs) -> ImportResult:
        """
        Importing "saved content" via the official API is not possible
        (see module docstring), so this always returns an empty,
        clearly-labeled result rather than pretending to import anything.
        """
        result = ImportResult()
        return result

    def fetch_own_published_media(self, limit=25):
        """
        Legitimate, narrower use of the official API: fetch the connected
        business/creator account's OWN published media (not Saved posts).
        Requires META_ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID to be configured.
        """
        if not self.access_token or not self.ig_account_id:
            return {
                "success": False,
                "error": {
                    "code": "INSTAGRAM_NOT_CONFIGURED",
                    "message": "META_ACCESS_TOKEN and/or INSTAGRAM_ACCOUNT_ID are not configured.",
                },
            }

        url = f"{GRAPH_API_BASE}/{self.ig_account_id}/media"
        params = {
            "fields": "id,caption,media_type,media_url,permalink,timestamp",
            "access_token": self.access_token,
            "limit": limit,
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
        except requests.RequestException as exc:
            return {
                "success": False,
                "error": {"code": "INSTAGRAM_API_UNREACHABLE", "message": str(exc)},
            }

        if resp.status_code == 401:
            return {
                "success": False,
                "error": {"code": "INSTAGRAM_TOKEN_EXPIRED", "message": "The Meta access token is invalid or expired."},
            }
        if resp.status_code != 200:
            return {
                "success": False,
                "error": {
                    "code": "INSTAGRAM_API_ERROR",
                    "message": f"Meta Graph API returned status {resp.status_code}: {resp.text[:300]}",
                },
            }

        return {"success": True, "data": resp.json().get("data", [])}
