import time
from pathlib import Path

from google import genai
from google.genai import types
from config import Config


VIDEO_FILE = Path("technical_reel.webm")

TRANSCRIPT = """
[00:00.000 --> 00:03.000] The world is moving, we were never meant to stay
[00:03.000 --> 00:06.000] But I was working on the world
[00:06.000 --> 00:09.000] I guess I thought later, but I gave you what I had
[00:09.000 --> 00:12.000] I guess I thought later, but what
"""

PROMPT = f"""
You are analyzing one Instagram Reel for a software-engineering-focused
saved-content library.

Your goal is to understand what the Reel actually contains and determine
whether it contains useful technical/software-development knowledge.

IMPORTANT EVIDENCE RULES:

1. The attached video is the PRIMARY evidence.
   Analyze the actual visual content, on-screen text, demonstrations,
   code, diagrams, and spoken content in the video.

2. The following transcript was generated automatically by Whisper:
{TRANSCRIPT}

3. The Whisper transcript MAY contain:
   - background music
   - song lyrics
   - unrelated audio
   - transcription errors

   Therefore, DO NOT assume that the transcript represents the creator's
   speech or explanation.

   Treat the transcript as supporting evidence ONLY when it is clearly
   relevant to the subject of the Reel.

4. Do not hallucinate information that is not supported by the video.

5. If the Reel contains technical information, explain what is actually
   demonstrated or stated.

6. If the Reel is not technically useful, say so.

Return ONLY valid JSON with this structure:

{{
  "summary": "...",
  "technical_topic": "...",
  "key_points": [],
  "technologies": [],
  "tools": [],
  "actionable_steps": [],
  "difficulty": "BEGINNER|INTERMEDIATE|ADVANCED|UNKNOWN",
  "is_technically_useful": true,
  "transcript_relevance": "RELEVANT|POSSIBLY_RELEVANT|LIKELY_MUSIC_OR_LYRICS|IRRELEVANT|UNKNOWN",
  "transcript_reason": "...",
  "evidence_used": [],
  "limitations": [],
  "confidence": 0.0
}}

Metadata:
URL: https://www.instagram.com/srii_tech_/reel/Dar2Mk6xOQh/
Creator: srii_tech_
Media type: VIDEO
"""


def main():
    if not Config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    if not VIDEO_FILE.exists():
        raise RuntimeError(f"Video file not found: {VIDEO_FILE}")

    client = genai.Client(api_key=Config.GEMINI_API_KEY)

    print("Uploading video to Gemini...")
    video_file = client.files.upload(file=VIDEO_FILE)

    print("Uploaded file:", video_file.name)
    print("Initial state:", video_file.state)

    while not video_file.state or video_file.state.name != "ACTIVE":
        print("Waiting for Gemini to process the video...")
        time.sleep(2)
        video_file = client.files.get(name=video_file.name)
        print("File state:", video_file.state)

    print("\nVideo is ACTIVE.")
    print("Sending exactly ONE Gemini analysis request...")

    response = client.models.generate_content(
        model=Config.GEMINI_MODEL,
        contents=[
            types.Part.from_uri(
                file_uri=video_file.uri,
                mime_type=video_file.mime_type,
            ),
            PROMPT,
        ],
        config={
            "temperature": 0.2,
            "response_mime_type": "application/json",
        },
    )

    print("\n===== GEMINI RESPONSE =====\n")
    print(response.text)


if __name__ == "__main__":
    main()
