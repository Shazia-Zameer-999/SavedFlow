"""
Local Instagram Reel video/audio capture.

This module uses the user's existing authenticated Playwright profile
to open one Reel and capture its video + audio into a temporary WebM file.

It does not call Gemini or modify MongoDB.
"""

from pathlib import Path
from typing import Any

from playwright.sync_api import Page


def capture_reel(
    page: Page,
    reel_url: str,
    output_path: str | Path,
) -> dict[str, Any]:
    """
    Open one Instagram Reel in an existing Playwright page and capture
    its video + audio.

    The caller owns the Playwright browser/context.
    """

    output_path = Path(output_path)

    print(f"Opening Reel: {reel_url}")

    page.goto(
        reel_url,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    page.wait_for_timeout(5000)

    video = page.locator("video").first

    if video.count() == 0:
        raise RuntimeError("No video element found on the Reel.")

    info = video.evaluate("""
        video => ({
            duration: video.duration,
            currentTime: video.currentTime,
            width: video.videoWidth,
            height: video.videoHeight,
            paused: video.paused,
            muted: video.muted
        })
    """)

    duration = info["duration"]

    if not isinstance(duration, (int, float)) or duration <= 0:
        raise RuntimeError(
            f"Invalid Reel duration: {duration!r}"
        )

    print("Video information:")
    print(info)

    started = video.evaluate("""
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
        raise RuntimeError(started["error"])

    print(f"Video tracks: {started['videoTracks']}")
    print(f"Audio tracks: {started['audioTracks']}")

    # Start from the beginning.
    video.evaluate("""
        video => {
            video.currentTime = 0;
            video.play();
        }
    """)

    current_time = 0.0

    for _ in range(20):
        current_time = video.evaluate(
            "video => video.currentTime"
        )

        if current_time <= 0.1:
            break

        page.wait_for_timeout(100)

    print(
        f"Video position before recording: "
        f"{current_time:.3f}s"
    )

    record_seconds = duration + 0.5

    print(
        f"Recording the Reel for "
        f"{record_seconds:.2f} seconds..."
    )

    page.wait_for_timeout(
        int(record_seconds * 1000)
    )

    video.evaluate("""
        video => {
            if (
                window.__savedflowRecorder &&
                window.__savedflowRecorder.state !== "inactive"
            ) {
                window.__savedflowRecorder.stop();
            }
        }
    """)

    for _ in range(50):
        done = video.evaluate(
            "video => window.__savedflowRecordingDone === true"
        )

        if done:
            break

        page.wait_for_timeout(100)

    result = video.evaluate(
        "video => window.__savedflowRecordingResult"
    )

    if not result:
        raise RuntimeError(
            "Recording result was not created."
        )

    output = bytes(result["data"])
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    output_path.write_bytes(output)

    if not output:
        raise RuntimeError(
            "Captured Reel produced an empty file."
        )

    print(
        f"Saved Reel capture to: {output_path}"
    )
    print(
        f"File size: {len(output):,} bytes"
    )

    return {
        "path": str(output_path),
        "size": len(output),
        "duration": duration,
        "width": info["width"],
        "height": info["height"],
        "video_tracks": started["videoTracks"],
        "audio_tracks": started["audioTracks"],
    }
