"""
AI analysis pipeline (section 11) and structured-output validation
(section 12).

determine_available_content() decides, honestly, what information we
actually have for a given item (section 4: never claim to have watched a
video that wasn't legitimately retrieved). For V1, SavedFlow does not
implement an authorized video/audio retrieval path, so the basis is
METADATA_ONLY unless a transcript has been manually attached to the item
via user_notes/transcript fields - the pipeline is still structured so a
future transcript/frame extraction step can plug in without changing this
file's public interface.
"""
from models.analysis import ANALYSIS_SCHEMA_FIELDS, BASIS_TYPES
from services.ai.client import AIClient, AIClientError
from services.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from services.media.transcript import get_transcript_if_available

REQUIRED_LIST_FIELDS = [
    "key_takeaways", "dev_tricks", "technical_concepts", "tools_mentioned",
    "technologies_mentioned", "libraries_mentioned", "actionable_steps",
    "potential_limitations", "claims_to_verify",
]
REQUIRED_SCORE_FIELDS = [
    "practicality_score", "learning_value_score", "implementation_value_score",
    "development_relevance_score", "originality_score", "overall_usefulness_score",
    "confidence",
]
VALID_DIFFICULTIES = {"BEGINNER", "INTERMEDIATE", "ADVANCED"}
VALID_RECOMMENDATIONS = {"WATCH_NOW", "WATCH_LATER", "WORTH_IMPLEMENTING", "LOW_VALUE", "SKIP"}


class AnalysisValidationError(Exception):
    pass


def determine_available_content(item):
    """
    Decide what legitimate content we can offer the AI for this item
    (section 4 / section 11). Never claims video/audio access we don't have.
    """
    transcript = get_transcript_if_available(item)
    if transcript:
        return {
            "basis": "TRANSCRIPT",
            "transcript": transcript,
            "caption": item.get("caption"),
        }
    if item.get("caption"):
        return {"basis": "METADATA_ONLY", "caption": item.get("caption")}
    return {"basis": "METADATA_ONLY", "caption": None}


def validate_structured_output(data):
    """
    Validate the AI's JSON output against the schema in section 12.
    Raises AnalysisValidationError with a clear message on any problem -
    callers use this to decide whether to mark the job FAILED.
    """
    if not isinstance(data, dict):
        raise AnalysisValidationError("AI output is not a JSON object.")

    for field in REQUIRED_LIST_FIELDS:
        if field not in data or not isinstance(data[field], list):
            raise AnalysisValidationError(f"Field '{field}' must be a list.")

    for field in REQUIRED_SCORE_FIELDS:
        if field not in data or not isinstance(data[field], (int, float)):
            raise AnalysisValidationError(f"Field '{field}' must be a number.")
        if not (0 <= data[field] <= 100):
            raise AnalysisValidationError(f"Field '{field}' must be between 0 and 100.")

    for field in ("summary", "core_idea", "problem_solved", "why_useful", "who_should_use_it"):
        if field not in data or not isinstance(data[field], str):
            raise AnalysisValidationError(f"Field '{field}' must be a string.")

    if data.get("difficulty") not in VALID_DIFFICULTIES:
        raise AnalysisValidationError("Field 'difficulty' must be one of BEGINNER/INTERMEDIATE/ADVANCED.")

    if data.get("recommendation") not in VALID_RECOMMENDATIONS:
        raise AnalysisValidationError(
            "Field 'recommendation' must be one of WATCH_NOW/WATCH_LATER/WORTH_IMPLEMENTING/LOW_VALUE/SKIP."
        )

    # Normalize scores to plain ints for storage.
    for field in REQUIRED_SCORE_FIELDS:
        data[field] = int(round(data[field]))

    return data


def analyze_item(item, ai_client: AIClient = None):
    """
    Run the full AI analysis pipeline for a single item and return
    (analysis_basis, validated_structured_output).
    Raises AIClientError or AnalysisValidationError on failure - the caller
    (services/jobs/manager.py) is responsible for turning that into a
    FAILED job rather than corrupting the database.
    """
    ai_client = ai_client or AIClient()
    available = determine_available_content(item)

    if not ai_client.is_configured():
        raise AIClientError("GEMINI_API_KEY is not configured.")

    user_prompt = build_user_prompt(item, available)
    raw = ai_client.complete_json(SYSTEM_PROMPT, user_prompt)
    parsed = ai_client.parse_json(raw)
    validated = validate_structured_output(parsed)
    return available["basis"], validated
