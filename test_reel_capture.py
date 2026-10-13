import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright


REEL_URL = sys.argv[1]
OUTPUT_FILE = Path(sys.argv[2] if len(sys.argv) > 2 else "test_reel_audio_new.webm")
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
        await page.goto(REEL_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(5000)

        video = page.locator("video").first

        if await video.count() == 0:
            print("ERROR: No video element found.")
            await context.close()
            return

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

        await video.evaluate("""
            video => {
                video.muted = false;
                video.volume = 1;
            }
        """)

        print("Starting audio capture...")

        started = await video.evaluate("""
            video => {
                const stream = video.captureStream();
                const audioTracks = stream.getAudioTracks();

                if (!audioTracks.length) {
                    return { error: "No audio track found." };
                }

                const audioStream = new MediaStream(audioTracks);

                window.__savedflowAudioChunks = [];

                const recorder = new MediaRecorder(
                    audioStream,
                    { mimeType: "audio/webm;codecs=opus" }
                );

                recorder.ondataavailable = event => {
                    if (event.data.size > 0) {
                        window.__savedflowAudioChunks.push(event.data);
                    }
                };

                window.__savedflowAudioRecorder = recorder;

                recorder.start();

                return {
                    started: true,
                    audioTracks: audioTracks.length
                };
            }
        """)

        if "error" in started:
            print("ERROR:", started["error"])
            await context.close()
            return

        print(f"Audio tracks: {started['audioTracks']}")
        print("Recording for 12 seconds...")

        await page.wait_for_timeout(12000)

        result = await video.evaluate("""
            async video => {
                const recorder = window.__savedflowAudioRecorder;

                if (!recorder) {
                    return { error: "Recorder not found." };
                }

                if (recorder.state !== "inactive") {
                    recorder.stop();
                }

                await new Promise(resolve => {
                    if (recorder.state === "inactive") {
                        resolve();
                    } else {
                        recorder.onstop = resolve;
                    }
                });

                const blob = new Blob(
                    window.__savedflowAudioChunks,
                    { type: "audio/webm;codecs=opus" }
                );

                const buffer = await blob.arrayBuffer();

                return {
                    size: buffer.byteLength,
                    data: Array.from(new Uint8Array(buffer))
                };
            }
        """)

        if "error" in result:
            print("ERROR:", result["error"])
            await context.close()
            return

        output = bytes(result["data"])
        OUTPUT_FILE.write_bytes(output)

        print(f"Saved audio to: {OUTPUT_FILE}")
        print(f"File size: {len(output):,} bytes")

        await context.close()


asyncio.run(main())
