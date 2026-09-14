"""User-run local Saved discovery helper.

Usage: python scripts/instagram_saved_sync.py --profile ./local-instagram-profile
The first run opens a visible browser so the user can log in manually. The
profile is local-only and must never be committed or uploaded.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--server", default="http://127.0.0.1:5000")
    parser.add_argument(
        "--saved-url",
        default=os.environ.get("INSTAGRAM_SAVED_URL", ""),
        help="Your account-specific Saved URL, e.g. https://www.instagram.com/your_username/saved/",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Print discovered link candidates and exit without importing.",
    )
    args = parser.parse_args()
    if not args.saved_url:
        print("Provide --saved-url https://www.instagram.com/<your_username>/saved/", file=sys.stderr)
        return 2
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Install the optional dependency with: pip install playwright && playwright install chromium", file=sys.stderr)
        return 2
    with sync_playwright() as pw:
        try:
            context = pw.chromium.launch_persistent_context(
                str(Path(args.profile).expanduser()), headless=False, accept_downloads=False
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000)
            input("Complete login or any security check in the visible browser, then press Enter here... ")
            saved_url = args.saved_url.rstrip("/")
            if saved_url.endswith("/saved"):
                saved_url += "/all-posts"
            page.goto(saved_url + "/", wait_until="domcontentloaded", timeout=30000)
            # Saved cards are rendered lazily; give the grid time to hydrate
            # and scroll a few viewports so incremental saves are discovered.
            for _ in range(4):
                page.wait_for_timeout(1200)
                page.mouse.wheel(0, 1400)
            if "/accounts/login" in page.url:
                status = "AUTH_REQUIRED"
                items = []
            elif any(word in page.locator("body").inner_text().lower() for word in ("challenge", "confirm it's you", "suspicious login")):
                status = "LOGIN_CHALLENGE"
                items = []
            else:
                cards = page.locator("a[href]").evaluate_all("""els => els.map(e => {
                    const image = e.querySelector('img');
                    return {
                      href: e.href,
                      thumbnail_url: image?.currentSrc || image?.src || null,
                      visible_label: e.getAttribute('aria-label') || image?.alt || null
                    };
                })""")
                items = []
                seen_hrefs = set()
                for card in cards:
                    href = card.get("href")
                    if not href or href in seen_hrefs:
                        continue
                    seen_hrefs.add(href)
                    discovered = urljoin(page.url, href)
                    # Saved-page anchors are often /saved/reel/<code> or
                    # /saved/p/<code>; the API stores the canonical public URL.
                    discovered = discovered.replace("/saved/reel/", "/reel/")
                    discovered = discovered.replace("/saved/reels/", "/reels/")
                    discovered = discovered.replace("/saved/p/", "/p/")
                    path = discovered.split("?", 1)[0].rstrip("/")
                    parts = path.split("/")
                    # Require a real shortcode; this excludes navigation such
                    # as /reels/ and /<username>/reels/.
                    if len(parts) >= 3 and parts[-2] in {"reel", "reels", "p", "tv"} and len(parts[-1]) >= 5:
                        items.append({
                            "url": discovered,
                            "thumbnail_url": card.get("thumbnail_url"),
                            "visible_label": card.get("visible_label"),
                        })
                status = "COMPLETED"
            if args.diagnose:
                canonical = []
                for item in items:
                    match = re.search(r"/(reel|reels|p|tv)/([A-Za-z0-9_-]+)", item["url"])
                    canonical.append(
                        f"https://instagram.com/{'reel' if match.group(1) == 'reels' else match.group(1)}/{match.group(2)}"
                        if match else item["url"]
                    )
                print(json.dumps({
                    "status": status,
                    "raw_candidate_count": len(items),
                    "unique_canonical_count": len(set(canonical)),
                    "candidates": items,
                    "canonical_urls": canonical,
                }, indent=2))
                context.close()
                return 0
            payload = json.dumps({"source": "local_playwright", "status": status, "items": items}).encode()
            request = Request(urljoin(args.server, "/api/instagram/sync"), data=payload, headers={"Content-Type": "application/json"})
            print(urlopen(request, timeout=15).read().decode())
            context.close()
            return 0
        except Exception as exc:
            print(json.dumps({"success": False, "status": "BROWSER_UNAVAILABLE", "error": str(exc)}))
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
