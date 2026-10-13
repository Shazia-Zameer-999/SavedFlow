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
from services.media.evidence import collect_evidence

REQUIRED_LIST_FIELDS = [
    "key_takeaways",
    "dev_tricks",
    "technical_concepts",
    "tools_mentioned",
    "technologies_mentioned",
    "libraries_mentioned",
    "actionable_steps",
    "potential_limitations",
    "claims_to_verify",
    "evidence_used",
    "content_creation",
]
REQUIRED_SCORE_FIELDS = [
    "practicality_score",
    "learning_value_score",
    "implementation_value_score",
    "development_relevance_score",
    "originality_score",
    "overall_usefulness_score",
    "confidence",
]
VALID_DIFFICULTIES = {"BEGINNER", "INTERMEDIATE", "ADVANCED"}
VALID_RECOMMENDATIONS = {
    "WATCH_NOW",
    "WATCH_LATER",
    "WORTH_IMPLEMENTING",
    "LOW_VALUE",
    "SKIP",
}
VALID_TRANSCRIPT_RELEVANCE = {
    "RELEVANT",
    "PARTIALLY_RELEVANT",
    "LIKELY_MUSIC_OR_LYRICS",
    "UNRELATED",
    "UNRELIABLE",
    "NOT_AVAILABLE",
}


class AnalysisValidationError(Exception):
    pass


def determine_available_content(item):
    """
    Decide what legitimate content we can offer the AI for this item
    (section 4 / section 11). Never claims video/audio access we don't have.
    """
    video_path = item.get("local_video_path")
    transcript = get_transcript_if_available(item)
    if transcript:
        return {
            "basis": "VIDEO" if video_path else "TRANSCRIPT",
            "video_path": video_path,
            "transcript": transcript,
            "caption": item.get("caption"),
        }
    if item.get("caption"):
        return {
            "basis": "VIDEO" if video_path else "METADATA_ONLY",
            "video_path": video_path,
            "caption": item.get("caption"),
        }

    visible_label = (item.get("source_metadata") or {}).get("visible_label")
    if visible_label:
        return {
            "basis": "VIDEO" if video_path else "METADATA_ONLY",
            "video_path": video_path,
            "caption": visible_label,
        }

    return {
        "basis": "VIDEO" if video_path else "METADATA_ONLY",
        "video_path": video_path,
        "caption": None,
    }


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

    for field in (
        "summary",
        "technical_topic",
        "core_idea",
        "problem_solved",
        "why_useful",
        "who_should_use_it",
        "transcript_reason",
    ):
        if field not in data or not isinstance(data[field], str):
            raise AnalysisValidationError(f"Field '{field}' must be a string.")

    if "implementation" not in data or not isinstance(data["implementation"], dict):
        raise AnalysisValidationError("Field 'implementation' must be an object.")

    if data.get("transcript_relevance") not in VALID_TRANSCRIPT_RELEVANCE:
        raise AnalysisValidationError(
            "Field 'transcript_relevance' has an invalid value."
        )

    implementation = data.get("implementation")
    required_implementation_fields = {
        "can_implement",
        "steps",
        "required_tools",
        "estimated_effort",
        "reason",
    }
    if not isinstance(implementation, dict):
        raise AnalysisValidationError("Field 'implementation' must be an object.")
    if not required_implementation_fields.issubset(implementation):
        raise AnalysisValidationError(
            "Field 'implementation' is missing required fields."
        )
    if not isinstance(implementation["can_implement"], bool):
        raise AnalysisValidationError("implementation.can_implement must be a boolean.")
    if not isinstance(implementation["steps"], list):
        raise AnalysisValidationError("implementation.steps must be a list.")
    if not isinstance(implementation["required_tools"], list):
        raise AnalysisValidationError("implementation.required_tools must be a list.")
    if not isinstance(implementation["estimated_effort"], str):
        raise AnalysisValidationError(
            "implementation.estimated_effort must be a string."
        )
    if not isinstance(implementation["reason"], str):
        raise AnalysisValidationError("implementation.reason must be a string.")

    if not isinstance(data["evidence_used"], list):
        raise AnalysisValidationError("Field 'evidence_used' must be a list.")
    for evidence in data["evidence_used"]:
        if not isinstance(evidence, dict):
            raise AnalysisValidationError("Each evidence_used entry must be an object.")
        if not isinstance(evidence.get("type"), str):
            raise AnalysisValidationError("Each evidence_used.type must be a string.")
        if not isinstance(evidence.get("description"), str):
            raise AnalysisValidationError(
                "Each evidence_used.description must be a string."
            )

    if not isinstance(data["content_creation"], list):
        raise AnalysisValidationError("Field 'content_creation' must be a list.")
    for idea in data["content_creation"]:
        if not isinstance(idea, dict):
            raise AnalysisValidationError(
                "Each content_creation entry must be an object."
            )
        required_content_fields = {
            "title",
            "format",
            "hook",
            "concept",
            "original_angle",
            "why_it_could_work",
        }
        if not required_content_fields.issubset(idea):
            raise AnalysisValidationError(
                "A content_creation entry is missing required fields."
            )

    if data.get("difficulty") not in VALID_DIFFICULTIES:
        raise AnalysisValidationError(
            "Field 'difficulty' must be one of BEGINNER/INTERMEDIATE/ADVANCED."
        )

    if data.get("recommendation") not in VALID_RECOMMENDATIONS:
        raise AnalysisValidationError(
            "Field 'recommendation' must be one of WATCH_NOW/WATCH_LATER/WORTH_IMPLEMENTING/LOW_VALUE/SKIP."
        )

    # Normalize scores to plain ints for storage.
    for field in REQUIRED_SCORE_FIELDS:
        data[field] = int(round(data[field]))

    return data


def analyze_item(
    item,
    ai_client: AIClient = None,
    evidence=None,
):
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

    video_path = available.get("video_path")

    if video_path and evidence is None:
        evidence = collect_evidence(
            video_path=video_path,
            duration=item.get("video_duration"),
            output_dir=item.get(
                "evidence_output_dir",
                "/tmp/savedflow-evidence",
            ),
        )

    if evidence:
        available["transcript"] = evidence["transcript"]
        available["transcript_source"] = evidence["transcript_source"]
        available["frames"] = evidence["frames"]

    user_prompt = build_user_prompt(item, available)

    if video_path:
        raw = ai_client.complete_json_with_video(
            SYSTEM_PROMPT,
            user_prompt,
            video_path,
            frame_paths=available.get("frames"),
        )
    else:
        raw = ai_client.complete_json(SYSTEM_PROMPT, user_prompt)

    parsed = ai_client.parse_json(raw)
    validated = validate_structured_output(parsed)
    return available["basis"], validated
