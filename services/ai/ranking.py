"""
Deterministic, transparent ranking (section 14).

The formula is intentionally simple arithmetic on the scores the AI
already produced (plus watched/applied penalties), so it's easy to test,
easy to explain to the user, and easy to tweak later. No hidden ML model.
"""

WEIGHTS = {
    "development_relevance_score": 0.30,
    "implementation_value_score": 0.25,
    "practicality_score": 0.20,
    "learning_value_score": 0.15,
    "originality_score": 0.10,
}

ALREADY_WATCHED_PENALTY = 5
ALREADY_APPLIED_PENALTY = 15


def compute_overall_score(analysis, item, personal_relevance_bonus=0):
    """
    overall score =
        weighted sum of (development relevance, implementation value,
        practicality, learning value, originality)
        + personal relevance bonus
        - already watched penalty
        - already applied penalty

    Returns an int clamped to [0, 100], plus a breakdown dict explaining
    exactly how the number was produced (so recommendations can show
    "why" - section 16).
    """
    breakdown = {}
    weighted_sum = 0.0
    for field, weight in WEIGHTS.items():
        value = analysis.get(field, 0) or 0
        contribution = value * weight
        breakdown[field] = {"value": value, "weight": weight, "contribution": round(contribution, 2)}
        weighted_sum += contribution

    breakdown["personal_relevance_bonus"] = personal_relevance_bonus
    weighted_sum += personal_relevance_bonus

    watched_penalty = ALREADY_WATCHED_PENALTY if (item.get("watch_count") or 0) > 0 else 0
    applied_penalty = ALREADY_APPLIED_PENALTY if item.get("status") == "APPLIED" else 0
    breakdown["already_watched_penalty"] = -watched_penalty
    breakdown["already_applied_penalty"] = -applied_penalty
    weighted_sum -= watched_penalty
    weighted_sum -= applied_penalty

    overall = max(0, min(100, round(weighted_sum)))
    return overall, breakdown
