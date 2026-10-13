"""Representative frame extraction from captured, user-accessible video."""


def get_frames_if_available(item):
    return None


def extract_frames(
    video_path,
    output_dir,
    count=6,
    duration=None,
):
    """
    Extract representative JPEG frames from a captured video.

    Returns a list of generated frame paths.
    """

    import subprocess
    from pathlib import Path

    video_path = Path(video_path)
    output_dir = Path(output_dir)

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if count <= 0:
        raise ValueError("Frame count must be greater than zero.")

    if duration is None or duration <= 0:
        raise ValueError("A valid video duration is required.")

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_pattern = output_dir / "frame_%02d.jpg"

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"fps={count}/{duration}",
        "-q:v",
        "2",
        str(output_pattern),
    ]

    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )

    frames = sorted(output_dir.glob("frame_*.jpg"))

    return [str(path) for path in frames]
