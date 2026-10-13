"""Explicit, local evidence capture for a single requested analysis."""

import shutil
import tempfile
from pathlib import Path

from config import Config
from services.media.evidence import collect_evidence
from services.media.evidence_store import store_evidence
from utils.urls import normalize_instagram_url


class EvidenceCaptureError(Exception):
    """The local worker could not acquire evidence for an explicitly requested item."""


def capture_and_store_evidence(db, item, on_stage=None):
    """Capture one Reel through the configured local Playwright profile.

    This function is called only by an explicit AI job. It leaves Instagram
    credentials on the local machine, stores durable evidence in GridFS, and
    removes its temporary working files before returning.
    """

    profile = (Config.INSTAGRAM_BROWSER_PROFILE or "").strip()
    if not profile:
        raise EvidenceCaptureError(
            "INSTAGRAM_BROWSER_PROFILE is not configured for the local worker."
        )

    url = normalize_instagram_url(item.get("url"))
    if not url:
        raise EvidenceCaptureError("The item does not have a valid Instagram URL.")

    profile_path = Path(profile).expanduser()
    if not profile_path.exists() or not profile_path.is_dir():
        raise EvidenceCaptureError(
            "The configured Instagram browser profile is unavailable."
        )

    try:
        from playwright.sync_api import sync_playwright
        from services.media.video import capture_reel
    except ImportError as exc:
        raise EvidenceCaptureError(
            "Playwright is not installed for the local worker."
        ) from exc

    temp_dir = Path(tempfile.mkdtemp(prefix="savedflow-evidence-"))
    try:
        video_path = temp_dir / "reel.webm"
        if on_stage:
            on_stage("CAPTURING_VIDEO")
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(profile_path), headless=False
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                capture = capture_reel(page, url, video_path)
            finally:
                context.close()

        if on_stage:
            on_stage("EXTRACTING_EVIDENCE")
        evidence = collect_evidence(
            video_path=capture["path"],
            duration=capture["duration"],
            output_dir=temp_dir / "derived",
            on_stage=on_stage,
        )
        if on_stage:
            on_stage("STORING_EVIDENCE")
        return store_evidence(
            db=db,
            evidence=evidence,
            item_id=item["_id"],
            source_url=url,
        )
    except EvidenceCaptureError:
        raise
    except Exception as exc:
        raise EvidenceCaptureError(f"Evidence capture failed: {exc}") from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
