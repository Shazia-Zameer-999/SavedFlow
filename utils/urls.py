import re
from urllib.parse import urlparse

INSTAGRAM_HOST_RE = re.compile(
    r"^(?:www\.)?instagram\.com$",
    re.IGNORECASE,
)


PATH_RE = re.compile(
    r"^/?" r"(?:[A-Za-z0-9._-]+/)?" r"(reel|reels|p|tv)" r"/([A-Za-z0-9_-]+)/?$"
)


MARKDOWN_URL_RE = re.compile(
    r"^(?:!\[[^\]]*\]|\[[^\]]*\])\s*\((https?://[^)\s]+)\)\s*$",
    re.IGNORECASE,
)
RAW_URL_RE = re.compile(r"https?://[^\s)\]>\"'`]+", re.IGNORECASE)


def _clean_url(url):
    """
    Accept either a normal URL or a Markdown-style URL:

    https://instagram.com/reel/ABC123/

    [https://instagram.com/reel/ABC123/](https://instagram.com/reel/ABC123/)
    """
    if not isinstance(url, str):
        return None

    url = url.strip()

    markdown_match = MARKDOWN_URL_RE.match(url)

    if markdown_match:
        url = markdown_match.group(1).strip()

    if not url.startswith(("http://", "https://")):
        raw_match = RAW_URL_RE.search(url)
        if raw_match:
            url = raw_match.group(0).strip()

    return url


def is_valid_instagram_url(url):
    url = _clean_url(url)

    if not url:
        return False

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    if not parsed.netloc:
        return False

    if not INSTAGRAM_HOST_RE.match(parsed.netloc):
        return False

    if not PATH_RE.match(parsed.path or ""):
        return False

    return True


def extract_shortcode(url):
    url = _clean_url(url)

    if not url:
        return None

    try:
        parsed = urlparse(url)
    except Exception:
        return None

    match = PATH_RE.match(parsed.path or "")

    if not match:
        return None

    return match.group(2)


def normalize_instagram_url(url):
    url = _clean_url(url)

    if not is_valid_instagram_url(url):
        return None

    parsed = urlparse(url)

    match = PATH_RE.match(parsed.path)

    if not match:
        return None

    kind, shortcode = match.group(1), match.group(2)

    if kind in ("reel", "reels"):
        media_kind = "reel"
    elif kind == "p":
        media_kind = "p"
    else:
        media_kind = "tv"

    return f"https://instagram.com/{media_kind}/{shortcode}"
