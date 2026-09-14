"""
AI analysis document schema (section 12) plus the "what did the AI actually
see" enum from section 4/11 - this is the field that keeps the system
honest about whether it analyzed real content or only metadata.
"""
from utils.dates import utcnow

BASIS_TYPES = {"VIDEO", "AUDIO", "TRANSCRIPT", "FRAMES", "METADATA_ONLY"}

ANALYSIS_SCHEMA_FIELDS = [
    "summary", "core_idea", "problem_solved", "key_takeaways", "dev_tricks",
    "technical_concepts", "tools_mentioned", "technologies_mentioned",
    "libraries_mentioned", "actionable_steps", "difficulty",
    "practicality_score", "learning_value_score", "implementation_value_score",
    "development_relevance_score", "originality_score", "overall_usefulness_score",
    "why_useful", "who_should_use_it", "potential_limitations", "claims_to_verify",
    "recommendation", "confidence",
]


def new_analysis(item_id, structured_output, analysis_basis, model, analysis_version=1, content_hash=None):
    now = utcnow()
    doc = {
        "item_id": item_id,
        "analysis_basis": analysis_basis if analysis_basis in BASIS_TYPES else "METADATA_ONLY",
        "model": model,
        "analysis_version": analysis_version,
        "content_hash": content_hash,
        "analyzed_at": now,
        "created_at": now,
    }
    doc.update(structured_output)
    return doc
