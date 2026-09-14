"""
Instagram URL validation and normalization (used by manual import,
export import, and duplicate detection).

The normalization is intentionally conservative: it only strips things
that are clearly not part of the identity of the post (query strings,
trailing slash, scheme, www, tracking params) so that two links to the
same post normalize to the same string without accidentally merging
different posts.
"""
import re
from urllib.parse import urlparse

INSTAGRAM_HOST_RE = re.compile(r"^(www\.)?instagram\.com$", re.IGNORECASE)

# Matches /reel/<shortcode>/, /p/<shortcode>/, /reels/<shortcode>/, /tv/<shortcode>/
PATH_RE = re.compile(r"^/(reel|reels|p|tv)/([A-Za-z0-9_-]+)/?$")


def is_valid_instagram_url(url):
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc or not INSTAGRAM_HOST_RE.match(parsed.netloc):
        return False
    if not PATH_RE.match(parsed.path or ""):
        return False
    return True


def extract_shortcode(url):
    """Return the Instagram shortcode (e.g. 'ABC123') from a valid URL, or None."""
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return None
    match = PATH_RE.match(parsed.path or "")
    if not match:
        return None
    return match.group(2)


def normalize_instagram_url(url):
    """
    Produce a canonical form of an Instagram URL for duplicate detection.

    Example:
        https://www.instagram.com/reel/ABC123/?igshid=xyz
        -> https://instagram.com/reel/ABC123
    """
    if not is_valid_instagram_url(url):
        return None
    parsed = urlparse(url.strip())
    media_kind = "reel"
    match = PATH_RE.match(parsed.path)
    kind, shortcode = match.group(1), match.group(2)
    if kind in ("reel", "reels"):
        media_kind = "reel"
    elif kind == "p":
        media_kind = "p"
    elif kind == "tv":
        media_kind = "tv"
    # Instagram shortcodes use a case-sensitive alphabet. We normalize only
    # the host, media kind, query string, and trailing slash; never the code.
    return f"https://instagram.com/{media_kind}/{shortcode}"
