import re
from urllib.parse import urlparse


INSTAGRAM_HOST_RE = re.compile(
    r"^(www\.)*?instagram\.com$",
    re.IGNORECASE,
)

PATH_RE = re.compile(
    r"^/?"
    r"(?:[A-Za-z0-9._]+/)?"
    r"(reel|reels|p|tv)"
    r"/([A-Za-z0-9_-]+)/?$"
)


def is_valid_instagram_url(url):
    if not isinstance(url, str) or not url.strip():
        return False

    try:
        parsed = urlparse(url.strip())
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
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return None

    match = PATH_RE.match(parsed.path or "")

    if not match:
        return None

    return match.group(2)


def normalize_instagram_url(url):
    if not is_valid_instagram_url(url):
        return None

    parsed = urlparse(url.strip())

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