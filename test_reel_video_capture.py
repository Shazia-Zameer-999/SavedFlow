import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright


REEL_URL = sys.argv[1]
OUTPUT_FILE = Path(
    sys.argv[2] if len(sys.argv) > 2 else "technical_reel.webm"
)
PROFILE_DIR = Path("./local-instagram-profile")


async def main():
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

        await video.evaluate("""
    video => new Promise(resolve => {
        if (Number.isFinite(video.duration) && video.duration > 0) {
            resolve();
            return;
        }

        const check = () => {
            if (Number.isFinite(video.duration) && video.duration > 0) {
                video.removeEventListener("loadedmetadata", check);
                resolve();
            }
        };

        video.addEventListener("loadedmetadata", check);
    })
""")

        info = await video.evaluate("""
            video => ({
                duration: video.duration,
                currentTime: video.currentTime,
                muted: video.muted,
                paused: video.paused,
                width: video.videoWidth,
                height: video.videoHeight
            })
        """)

        print("Video information:")
        print(info)

        duration = info["duration"]

        if not isinstance(duration, (int, float)) or duration <= 0:
            print("ERROR: Invalid video duration.")
            await context.close()
            return

        print("Video information:")
        print(info)

        print("Starting video + audio capture...")

        started = await video.evaluate("""
            video => {
                video.muted = false;
                video.volume = 1;

                const stream = video.captureStream();

                const videoTracks = stream.getVideoTracks();
                const audioTracks = stream.getAudioTracks();

                if (!videoTracks.length) {
                    return { error: "No video track found." };
                }

                window.__savedflowChunks = [];
                window.__savedflowRecordingDone = false;

                const recorder = new MediaRecorder(
                    stream,
                    { mimeType: "video/webm;codecs=vp8,opus" }
                );

                recorder.ondataavailable = event => {
                    if (event.data.size > 0) {
                        window.__savedflowChunks.push(event.data);
                    }
                };

                recorder.onstop = async () => {
                    const blob = new Blob(
                        window.__savedflowChunks,
                        { type: "video/webm;codecs=vp8,opus" }
                    );

                    const buffer = await blob.arrayBuffer();

                    window.__savedflowRecordingResult = {
                        size: buffer.byteLength,
                        data: Array.from(new Uint8Array(buffer))
                    };

                    window.__savedflowRecordingDone = true;
                };

                window.__savedflowRecorder = recorder;

                recorder.start(250);

                return {
                    started: true,
                    videoTracks: videoTracks.length,
                    audioTracks: audioTracks.length
                };
            }
        """)

        if "error" in started:
            print("ERROR:", started["error"])
            await context.close()
            return

        print(f"Video tracks: {started['videoTracks']}")
        print(f"Audio tracks: {started['audioTracks']}")

        # Start the Reel from the beginning.
        await video.evaluate("""
            video => {
                video.currentTime = 0;
                video.play();
            }
        """)

        # Wait until the browser actually reaches the beginning.
        for _ in range(20):
            current_time = await video.evaluate("video => video.currentTime")

            if current_time <= 0.1:
                break

            await page.wait_for_timeout(100)

        current_time = await video.evaluate("video => video.currentTime")

        print(f"Video position before recording: {current_time:.3f}s")

        record_seconds = duration + 0.5

        print(
            f"Recording the Reel for {record_seconds:.2f} seconds..."
        )

        await page.wait_for_timeout(
            int(record_seconds * 1000)
        )

        print("Stopping recording...")

        await video.evaluate("""
            video => {
                if (window.__savedflowRecorder &&
                    window.__savedflowRecorder.state !== "inactive") {
                    window.__savedflowRecorder.stop();
                }
            }
        """)

        # Wait for the onstop handler to finish creating the Blob.
        for _ in range(50):
            done = await video.evaluate(
                "video => window.__savedflowRecordingDone === true"
            )

            if done:
                break

            await page.wait_for_timeout(100)

        result = await video.evaluate(
            "video => window.__savedflowRecordingResult"
        )

        if not result:
            print("ERROR: Recording result was not created.")
            await context.close()
            return

        output = bytes(result["data"])
        OUTPUT_FILE.write_bytes(output)

        print(f"Saved video + audio to: {OUTPUT_FILE}")
        print(f"File size: {len(output):,} bytes")

        await context.close()


asyncio.run(main())
