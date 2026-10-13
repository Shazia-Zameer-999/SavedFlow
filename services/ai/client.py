"""
Gemini AI client wrapper.

This is the ONLY file that imports the Gemini SDK.
Everything else in SavedFlow continues to use:
    AIClient.complete_json(...)
"""

import json

from config import Config


class AIClientError(Exception):
    pass


class GeminiQuotaError(AIClientError):
    """A provider response indicates rate or quota exhaustion."""


def _wrap_gemini_error(prefix, exc):
    message = str(exc)
    if any(
        marker in message.upper()
        for marker in ("429", "RESOURCE_EXHAUSTED", "RATE LIMIT", "QUOTA")
    ):
        return GeminiQuotaError(f"{prefix}: {message}")
    return AIClientError(f"{prefix}: {message}")


class AIClient:
    def __init__(self, api_key=None, model=None):
        self.api_key = Config.GEMINI_API_KEY if api_key is None else api_key
        self.model = Config.GEMINI_MODEL if model is None else model
        self._client = None

    def is_configured(self):
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)

        return self._client

    def complete_json(self, system_prompt, user_prompt, temperature=0.2):
        """
        Send the prompt to Gemini and return the raw text response.

        The analyzer is responsible for parsing and validating JSON.
        """

        if not self.is_configured():
            raise AIClientError("GEMINI_API_KEY is not configured.")

        client = self._get_client()

        prompt = f"""
SYSTEM INSTRUCTIONS:
{system_prompt}

USER REQUEST:
{user_prompt}

IMPORTANT:
Return ONLY valid JSON.
Do not wrap the JSON in markdown code fences.
"""

        try:
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "temperature": temperature,
                    "response_mime_type": "application/json",
                },
            )
        except Exception as exc:
            raise _wrap_gemini_error("Gemini API error", exc) from exc

        text = getattr(response, "text", None)

        if not text:
            raise AIClientError("Gemini returned an empty response.")

        return text

    def complete_json_with_video(
        self,
        system_prompt,
        user_prompt,
        video_path,
        frame_paths=None,
        temperature=0.2,
    ):
        """
        Send a local video to Gemini together with the analysis prompt
        and return the raw JSON response.
        """

        if not self.is_configured():
            raise AIClientError("GEMINI_API_KEY is not configured.")

        video_path = str(video_path)

        client = self._get_client()

        try:
            uploaded_file = client.files.upload(file=video_path)

            frame_files = [
                client.files.upload(file=str(frame_path))
                for frame_path in (frame_paths or [])
            ]
            response = client.models.generate_content(
                model=self.model,
                contents=[
                    uploaded_file,
                    *frame_files,
                    f"""
SYSTEM INSTRUCTIONS:
{system_prompt}

USER REQUEST:
{user_prompt}

IMPORTANT:
Return ONLY valid JSON.
Do not wrap the JSON in markdown code fences.
""",
                ],
                config={
                    "temperature": temperature,
                    "response_mime_type": "application/json",
                },
            )
        except Exception as exc:
            raise _wrap_gemini_error("Gemini video analysis error", exc) from exc

        text = getattr(response, "text", None)

        if not text:
            raise AIClientError("Gemini returned an empty response.")

        return text

    @staticmethod
    def parse_json(raw_text):
        """Parse a JSON string, attempting a light repair pass first."""

        try:
            return json.loads(raw_text)
        except (json.JSONDecodeError, TypeError):
            pass

        cleaned = raw_text.strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")

            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()

        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, TypeError) as exc:
            raise AIClientError(f"AI response was not valid JSON: {exc}")
