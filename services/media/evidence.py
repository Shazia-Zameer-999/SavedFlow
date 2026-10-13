"""
Evidence collection for one locally captured Instagram Reel.

This module combines:
- the captured video/audio file,
- representative video frames,
- a local Whisper transcript.

It does not call Gemini or modify MongoDB.
"""

from pathlib import Path
from typing import Any

from services.media.frames import extract_frames
from services.media.transcript import transcribe_audio


def collect_evidence(
    video_path: str | Path,
    duration: float,
    output_dir: str | Path,
    frame_count: int = 6,
    whisper_model: str = "base",
    on_stage=None,
) -> dict[str, Any]:
    """
    Build an evidence package from one captured Reel.
    """

    video_path = Path(video_path)
    output_dir = Path(output_dir)

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    frames_dir = output_dir / "frames"

    try:
        if on_stage:
            on_stage("EXTRACTING_FRAMES")
        frames = extract_frames(
            video_path=video_path,
            output_dir=frames_dir,
            count=frame_count,
            duration=duration,
        )
    except Exception:
        # A valid captured video can still be useful evidence when ffmpeg is
        # unavailable or a codec cannot yield still frames.
        frames = []

    try:
        if on_stage:
            on_stage("TRANSCRIBING_AUDIO")
        transcript = transcribe_audio(
            video_path=video_path,
            model_name=whisper_model,
        )
        transcript_source = "WHISPER" if transcript else "NOT_AVAILABLE"
    except Exception:
        # Reels with no audio and machines without Whisper should still reach
        # visual analysis; do not discard the captured video for that reason.
        transcript = ""
        transcript_source = "NOT_AVAILABLE"

    return {
        "video_path": str(video_path),
        "duration": duration,
        "frames": frames,
        "transcript": transcript,
        "transcript_source": transcript_source,
    }
