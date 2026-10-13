import argparse
from pathlib import Path

from bson import ObjectId
from playwright.sync_api import sync_playwright

from app import create_app
from extensions import get_db
from services.media.evidence import collect_evidence
from services.media.evidence_store import store_evidence
from services.media.video import capture_reel
from utils.urls import normalize_instagram_url


PROFILE = "./local-instagram-profile"
OUTPUT_ROOT = Path("/tmp/savedflow-evidence")


def capture_one(url, output_path):
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            PROFILE,
            headless=False,
        )

        page = (
            context.pages[0]
            if context.pages
            else context.new_page()
        )

        print("Opening:", url)

        result = capture_reel(
            page=page,
            reel_url=url,
            output_path=output_path,
        )

        context.close()

        return result


def main():
    parser = argparse.ArgumentParser(
        description="Capture and store evidence for one SavedFlow item."
    )

    parser.add_argument(
        "--item-id",
        required=True,
        help="MongoDB instagram_items ObjectId",
    )

    args = parser.parse_args()

    try:
        item_id = ObjectId(args.item_id)
    except Exception:
        raise SystemExit("Invalid MongoDB item ID.")

    app = create_app()

    with app.app_context():
        db = get_db()

        item = db.instagram_items.find_one(
            {"_id": item_id}
        )

        if not item:
            raise SystemExit("Item not found.")

        normalized_url = normalize_instagram_url(
            item.get("url")
        )

        if not normalized_url:
            raise SystemExit(
                "Could not normalize the item's Instagram URL."
            )

        print("Item:", item["_id"])
        print("Stored URL:", item.get("url"))
        print("Normalized URL:", normalized_url)

        output_dir = OUTPUT_ROOT / str(item["_id"])
        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        video_path = output_dir / "reel.webm"

        print("\nCapturing Reel...")

        capture_result = capture_one(
            normalized_url,
            video_path,
        )

        print(
            "Captured:",
            capture_result["size"],
            "bytes",
        )
        print(
            "Duration:",
            capture_result["duration"],
            "seconds",
        )
        print(
            "Resolution:",
            capture_result["width"],
            "x",
            capture_result["height"],
        )
        print(
            "Video tracks:",
            capture_result["video_tracks"],
        )
        print(
            "Audio tracks:",
            capture_result["audio_tracks"],
        )

        print("\nCollecting frames and transcript...")

        evidence = collect_evidence(
            video_path=capture_result["path"],
            duration=capture_result["duration"],
            output_dir=output_dir / "evidence",
        )

        print(
            "Frames:",
            len(evidence["frames"]),
        )
        print(
            "Transcript source:",
            evidence["transcript_source"],
        )
        print(
            "Transcript:",
            evidence["transcript"],
        )

        print("\nStoring evidence in MongoDB/GridFS...")

        stored = store_evidence(
            db=db,
            evidence=evidence,
            item_id=item["_id"],
            source_url=normalized_url,
        )

        print("\nEvidence stored successfully.")
        print("Evidence ID:", stored["_id"])
        print("Video GridFS ID:", stored["video_file_id"])
        print(
            "Frame GridFS IDs:",
            len(stored["frame_file_ids"]),
        )


if __name__ == "__main__":
    main()
