"""Local Instagram Saved synchronization agent.

This script is intentionally local-only.

It uses a persistent Playwright browser profile so that the user's
Instagram authentication stays on their own computer.

The hosted SavedFlow server never receives the Instagram password,
cookies, or browser session.

Examples:

    python scripts/instagram_saved_sync.py --profile ./local-instagram-profile

    python scripts/instagram_saved_sync.py \
        --profile ./local-instagram-profile \
        --once

Configuration can be supplied through environment variables:

    SAVEDFLOW_SERVER_URL
    INSTAGRAM_SAVED_URL
    SAVEDFLOW_SYNC_TOKEN
    SYNC_INTERVAL_SECONDS
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from dotenv import load_dotenv

load_dotenv()


DEFAULT_INTERVAL = 60
SCROLL_DISTANCE = 1600
SCROLL_WAIT_MS = 1200
MAX_IDLE_ROUNDS = 5


def get_config(args):
    server = (args.server or os.environ.get("SAVEDFLOW_SERVER_URL", "")).rstrip("/")

    saved_url = (args.saved_url or os.environ.get("INSTAGRAM_SAVED_URL", "")).rstrip(
        "/"
    )

    token = args.token or os.environ.get("SAVEDFLOW_SYNC_TOKEN", "")

    try:
        interval = int(
            args.interval
            or os.environ.get(
                "SYNC_INTERVAL_SECONDS",
                DEFAULT_INTERVAL,
            )
        )
    except ValueError:
        interval = DEFAULT_INTERVAL

    return server, saved_url, token, max(interval, 10)


def require_config(server, saved_url, token):
    missing = []

    if not server:
        missing.append("SAVEDFLOW_SERVER_URL")

    if not saved_url:
        missing.append("INSTAGRAM_SAVED_URL")

    if not token:
        missing.append("SAVEDFLOW_SYNC_TOKEN")

    if missing:
        print(
            "Missing configuration: " + ", ".join(missing),
            file=sys.stderr,
        )
        return False

    return True


def post_json(url, payload, token):
    body = json.dumps(payload).encode("utf-8")

    request = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-SavedFlow-Sync-Token": token,
        },
        method="POST",
    )

    with urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(url, token):
    request = Request(
        url,
        headers={
            "X-SavedFlow-Sync-Token": token,
        },
        method="GET",
    )

    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def upload_thumbnail(
    server,
    token,
    image_bytes,
    source_url,
):
    boundary = "----SavedFlowThumbnailBoundary"

    body = b"".join(
        [
            (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="thumbnail"; '
                'filename="instagram-thumbnail.jpg"\r\n'
                "Content-Type: image/jpeg\r\n\r\n"
            ).encode("utf-8"),
            image_bytes,
            (
                f"\r\n--{boundary}\r\n"
                'Content-Disposition: form-data; name="source_url"\r\n\r\n'
                f"{source_url or ''}\r\n"
                f"--{boundary}--\r\n"
            ).encode("utf-8"),
        ]
    )

    request = Request(
        urljoin(
            server + "/",
            "api/instagram/sync/thumbnail",
        ),
        data=body,
        headers={
            "Content-Type": (f"multipart/form-data; boundary={boundary}"),
            "X-SavedFlow-Sync-Token": token,
        },
        method="POST",
    )

    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def attach_thumbnail_file_ids(
    context,
    server,
    token,
    items,
):
    """
    Download fresh Instagram thumbnails through the authenticated
    Playwright context and upload them to SavedFlow.
    """

    for index, item in enumerate(items):
        thumbnail_url = item.get("thumbnail_url")

        if not thumbnail_url:
            continue

        try:
            print(f"Downloading thumbnail " f"{index + 1}/{len(items)}...")

            response = context.request.get(
                thumbnail_url,
                timeout=30000,
            )

            if not response.ok:
                print(f"Thumbnail request failed: " f"{response.status}")
                continue

            image_bytes = response.body()

            if not image_bytes:
                print("Thumbnail response was empty.")
                continue

            upload_response = upload_thumbnail(
                server=server,
                token=token,
                image_bytes=image_bytes,
                source_url=thumbnail_url,
            )

            file_id = upload_response.get("thumbnail_file_id")

            if file_id:
                item["thumbnail_file_id"] = file_id
                print(f"Thumbnail stored: {file_id}")

        except Exception as exc:
            print(f"Could not store thumbnail: {exc}")

    return items


def discover_items(page):
    """
    Keep scrolling until Instagram stops producing new content.

    This is deliberately based on observed page growth instead of a fixed
    number of scrolls.
    """

    discovered = {}
    idle_rounds = 0

    while idle_rounds < MAX_IDLE_ROUNDS:
        before_count = len(discovered)

        page.wait_for_timeout(SCROLL_WAIT_MS)

        cards = page.locator("a[href]").evaluate_all("""els => els.map(e => {
                const image = e.querySelector('img');

                return {
                    href: e.href,
                    thumbnail_url:
                        image?.currentSrc ||
                        image?.src ||
                        null,
                    visible_label:
                        e.getAttribute('aria-label') ||
                        image?.alt ||
                        null
                };
            })""")

        for card in cards:
            href = card.get("href")

            if not href:
                continue

            discovered_url = urljoin(
                page.url,
                href,
            )

            discovered_url = (
                discovered_url.replace(
                    "/saved/reel/",
                    "/reel/",
                )
                .replace(
                    "/saved/reels/",
                    "/reels/",
                )
                .replace(
                    "/saved/p/",
                    "/p/",
                )
                .replace(
                    "/saved/tv/",
                    "/tv/",
                )
            )

            path = discovered_url.split("?", 1)[0].rstrip("/")

            parts = path.split("/")

            if (
                len(parts) >= 3
                and parts[-2]
                in {
                    "reel",
                    "reels",
                    "p",
                    "tv",
                }
                and len(parts[-1]) >= 5
            ):
                discovered[discovered_url] = {
                    "url": discovered_url,
                    "thumbnail_url": card.get("thumbnail_url"),
                    "visible_label": card.get("visible_label"),
                }

        after_count = len(discovered)

        if after_count == before_count:
            idle_rounds += 1
        else:
            idle_rounds = 0

        page.mouse.wheel(
            0,
            SCROLL_DISTANCE,
        )

    return list(discovered.values())


def check_auth(page):
    if "/accounts/login" in page.url:
        return "AUTH_REQUIRED"

    body = page.locator("body").inner_text().lower()

    challenge_words = (
        "challenge",
        "confirm it's you",
        "suspicious login",
    )

    if any(word in body for word in challenge_words):
        return "LOGIN_CHALLENGE"

    return "COMPLETED"


def run_sync(
    server,
    saved_url,
    token,
    profile_path,
    diagnose=False,
    thumbnail_limit=0,
):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Install Playwright with:\n"
            "pip install playwright\n"
            "playwright install chromium",
            file=sys.stderr,
        )
        return 2

    with sync_playwright() as pw:
        context = None

        try:
            print("GITHUB_ACTIONS =", repr(os.environ.get("GITHUB_ACTIONS")))
            if os.environ.get("GITHUB_ACTIONS") == "true":
                browser = pw.chromium.launch(headless=True)
                context = browser.new_context(
                    storage_state="instagram-state.json",
                    accept_downloads=False,
                )
            else:
                context = pw.chromium.launch_persistent_context(
                    str(Path(profile_path).expanduser().resolve()),
                    headless=False,
                    accept_downloads=False,
                )

            page = context.pages[0] if context.pages else context.new_page()

            print("Opening Instagram...")
            page.goto(
                "https://www.instagram.com/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            print(f"Instagram opened: {page.url}")

            if "/accounts/login" in page.url:
                if os.environ.get("GITHUB_ACTIONS") == "true":
                    print("Instagram login required on GitHub runner.")
                    return 2

                input(
                    "Log in to Instagram in the visible browser, "
                    "then press Enter here... "
                )

                print("Opening Saved collection...")
            page.goto(
                saved_url + "/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            print(f"Saved collection opened: {page.url}")

            status = check_auth(page)

            if status != "COMPLETED":
                items = []
            else:
                print("Starting item discovery...")
                items = discover_items(page)
                print(f"Item discovery finished: {len(items)} items found")

            result = {
                "status": status,
                "raw_candidate_count": len(items),
                "unique_canonical_count": len(items),
                "items": items,
            }

            if diagnose:
                print(
                    json.dumps(
                        result,
                        indent=2,
                    )
                )
                return 0
            if items:
                thumbnail_items = items

                if thumbnail_limit > 0:
                    thumbnail_items = items[:thumbnail_limit]

                print(
                    "Downloading and storing thumbnails "
                    f"for {len(thumbnail_items)} item(s)..."
                )

                attach_thumbnail_file_ids(
                    context=context,
                    server=server,
                    token=token,
                    items=thumbnail_items,
                )
            print("Sending discovered items to SavedFlow...")
            sync_response = post_json(
                urljoin(
                    server + "/",
                    "api/instagram/sync",
                ),
                {
                    "source": "local_playwright",
                    "status": status,
                    "items": items,
                },
                token,
            )

            print(
                json.dumps(
                    sync_response,
                    indent=2,
                )
            )

            return 0

        except Exception as exc:
            print(
                json.dumps(
                    {
                        "success": False,
                        "status": "BROWSER_UNAVAILABLE",
                        "error": str(exc),
                    }
                )
            )

            return 1

        finally:
            if context:
                context.close()
            if os.environ.get("GITHUB_ACTIONS") == "true":
                browser.close()


def process_pending_job(
    server,
    token,
    profile,
    thumbnail_limit=0,
):
    try:
        job = get_json(
            server + "/api/instagram/sync/pending",
            token,
        )
    except Exception as exc:
        print(
            f"Could not contact SavedFlow: {exc}",
            file=sys.stderr,
        )
        return

    if not job.get("pending"):
        return

    job_id = job["job_id"]
    collection_url = job.get("collection_url")

    print(f"Starting sync job {job_id}...")

    try:
        result = run_sync(
            server=server,
            saved_url=collection_url,
            token=token,
            profile_path=profile,
            diagnose=False,
            thumbnail_limit=thumbnail_limit,
        )

        status = "COMPLETED" if result == 0 else "FAILED"

        post_json(
            server + f"/api/instagram/sync/{job_id}/complete",
            {
                "status": status,
                "result": {
                    "exit_code": result,
                },
            },
            token,
        )

    except Exception as exc:
        try:
            post_json(
                server + f"/api/instagram/sync/{job_id}/complete",
                {
                    "status": "FAILED",
                    "error": str(exc),
                },
                token,
            )
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--profile",
        required=True,
        help="Persistent local Playwright profile directory.",
    )

    parser.add_argument(
        "--server",
        default="",
        help="Override SAVEDFLOW_SERVER_URL.",
    )

    parser.add_argument(
        "--saved-url",
        default="",
        help="Override INSTAGRAM_SAVED_URL.",
    )

    parser.add_argument(
        "--token",
        default="",
        help="Override SAVEDFLOW_SYNC_TOKEN.",
    )

    parser.add_argument(
        "--interval",
        default="",
        help="Polling interval in seconds.",
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Check once and exit.",
    )

    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Run discovery once and print discovered items.",
    )
    parser.add_argument(
        "--thumbnail-limit",
        type=int,
        default=0,
        help="Limit how many thumbnails are stored. 0 means all.",
    )

    args = parser.parse_args()

    server, saved_url, token, interval = get_config(args)

    if not require_config(
        server,
        saved_url,
        token,
    ):
        return 2

    if args.diagnose:
        return run_sync(
            server,
            saved_url,
            token,
            args.profile,
            diagnose=True,
        )

    print("SavedFlow local sync agent started.")
    print(f"Server: {server}")
    print(f"Collection: {saved_url}")
    print(f"Polling every {interval} seconds.")

    while True:
        process_pending_job(
            server,
            token,
            args.profile,
            thumbnail_limit=args.thumbnail_limit,
        )

        if args.once:
            break

        time.sleep(interval)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
