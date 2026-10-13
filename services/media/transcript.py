"""Transcript lookup and local Whisper transcription for captured video."""


def get_transcript_if_available(item):
    transcript = item.get("transcript")
    if isinstance(transcript, str) and transcript.strip():
        return transcript.strip()
    return None


def transcribe_audio(
    video_path,
    model_name="base",
):
    """
    Transcribe audio from a locally captured Reel video.

    This uses the locally installed Whisper package and does not
    call Gemini or modify MongoDB.
    """

    from pathlib import Path

    video_path = Path(video_path)

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    import whisper

    print(f"Loading Whisper model: {model_name}")

    model = whisper.load_model(model_name)

    print(f"Transcribing audio from: {video_path}")

    result = model.transcribe(
        str(video_path),
        fp16=False,
    )

    transcript = result.get("text", "").strip()

    return transcript
