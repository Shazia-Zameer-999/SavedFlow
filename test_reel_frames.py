import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright


REEL_URL = sys.argv[1]
OUTPUT_DIR = Path(sys.argv[2] if len(sys.argv) > 2 else "technical_reel_frames")
PROFILE_DIR = Path("./local-instagram-profile")


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            PROFILE_DIR,
            headless=False,
            accept_downloads=False,
        )

        page = await context.new_page()

        print(f"Opening: {REEL_URL}")

        await page.goto(
            REEL_URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        await page.wait_for_timeout(5000)

        video = page.locator("video").first

        if await video.count() == 0:
            print("ERROR: No video element found.")
            await context.close()
            return

        info = await video.evaluate("""
            video => ({
                duration: video.duration,
                width: video.videoWidth,
                height: video.videoHeight,
                paused: video.paused
            })
        """)

        print("Video information:")
        print(info)

        duration = info["duration"]

        # Capture approximately every 2 seconds.
        timestamps = [
            0.5,
            2.0,
            4.0,
            6.0,
            8.0,
            max(0.5, duration - 1.0),
        ]

        for index, timestamp in enumerate(timestamps, start=1):

            if timestamp >= duration:
                continue

            await video.evaluate(
                """(video, time) => {
                    video.currentTime = time;
                    video.pause();
                }""",
                timestamp,
            )

            await page.wait_for_timeout(500)

            frame = await video.screenshot(
                type="jpeg",
                quality=85,
            )

            output = OUTPUT_DIR / f"frame_{index:02d}_{timestamp:.1f}s.jpg"
            output.write_bytes(frame)

            print(
                f"Saved frame {index}: "
                f"{timestamp:.1f}s → {output}"
            )

        await context.close()

        print()
        print(f"Frames saved in: {OUTPUT_DIR}")


asyncio.run(main())
