"""
Process one Instagram Reel locally.

This script is intentionally controlled and local-only.
It captures exactly one Reel and collects its evidence.

It does not:
- modify MongoDB,
- create AI jobs,
- call Gemini.
"""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

from services.media.video import capture_reel
from services.media.evidence import collect_evidence
from services.ai.analyzer import analyze_item


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--profile",
        required=True,
        help="Persistent local Playwright profile directory.",
    )

    parser.add_argument(
        "--url",
        required=True,
        help="Instagram Reel URL to process.",
    )

    args = parser.parse_args()

    profile_path = (
        Path(args.profile)
        .expanduser()
        .resolve()
    )

    output_dir = Path("/tmp/savedflow-one-reel")
    video_path = output_dir / "reel.webm"
    evidence_dir = output_dir / "evidence"

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("Opening Instagram with local profile...")

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            str(profile_path),
            headless=False,
            accept_downloads=False,
        )

        try:
            page = (
                context.pages[0]
                if context.pages
                else context.new_page()
            )

            capture = capture_reel(
                page=page,
                reel_url=args.url,
                output_path=video_path,
            )

        finally:
            context.close()

    print("\n=== CAPTURE COMPLETE ===")
    print("Video:", capture["path"])
    print("Duration:", capture["duration"])
    print("Size:", capture["size"])
    print("Resolution:", capture["width"], "x", capture["height"])
    print("Video tracks:", capture["video_tracks"])
    print("Audio tracks:", capture["audio_tracks"])

    print("\nCollecting evidence...")

    evidence = collect_evidence(
        video_path=capture["path"],
        duration=capture["duration"],
        output_dir=evidence_dir,
        frame_count=6,
        whisper_model="base",
    )

    print("\n=== EVIDENCE COMPLETE ===")
    print("Video:", evidence["video_path"])
    print("Duration:", evidence["duration"])
    print("Frames:", len(evidence["frames"]))
    print("Transcript source:", evidence["transcript_source"])
    print("Transcript:", evidence["transcript"])

    print("\nFrame files:")
    for frame in evidence["frames"]:
        print(" -", frame)

    print("\nPreparing AI analysis...")

    item = {
        "url": args.url,
        "creator_username": None,
        "media_type": "VIDEO",
        "caption": None,
        "local_video_path": evidence["video_path"],
        "video_duration": evidence["duration"],
        "evidence_output_dir": str(evidence_dir),
    }

    print("Sending exactly one analysis request to Gemini...")

    basis, analysis = analyze_item(
        item,
        evidence=evidence,
    )

    print("\n=== AI ANALYSIS COMPLETE ===")
    print("Analysis basis:", basis)
    print("Summary:", analysis["summary"])
    print("Technical topic:", analysis["technical_topic"])
    print("Recommendation:", analysis["recommendation"])
    print("Transcript relevance:", analysis["transcript_relevance"])


if __name__ == "__main__":
    raise SystemExit(main())
