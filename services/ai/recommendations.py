"""
Recommendation engine (sections 15-18).

Combines AI scores with a transparent, additive personal-preference
weighting system. No black-box ML - every recommendation ships with a
human-readable `reason` string built from the same numbers used to rank it.
"""
from models.preference import DEFAULT_WEIGHT
from services.ai.ranking import compute_overall_score

PREFERENCE_BONUS_SCALE = 15  # weight (0-1) * scale => bonus points, max +15


def get_preference_weight(db, topic):
    if not topic:
        return DEFAULT_WEIGHT
    pref = db.user_preferences.find_one({"topic": topic})
    return pref["weight"] if pref else DEFAULT_WEIGHT


def personal_relevance_bonus(db, item):
    topic = item.get("category")
    weight = get_preference_weight(db, topic)
    return round((weight - DEFAULT_WEIGHT) * 2 * PREFERENCE_BONUS_SCALE, 2)


def build_reason(item, analysis, breakdown, overall_score):
    parts = []
    if breakdown["development_relevance_score"]["value"] >= 70:
        parts.append("high development relevance")
    if breakdown["implementation_value_score"]["value"] >= 70:
        parts.append("strong implementation value")
    if breakdown.get("personal_relevance_bonus", 0) > 0:
        parts.append("matches topics you frequently find useful")
    if breakdown["already_watched_penalty"] < 0:
        parts.append("slightly deprioritized because you've already watched it")
    if not parts:
        parts.append(f"an overall usefulness score of {overall_score}")
    return "Recommended due to " + ", ".join(parts) + "."


def _score_item(db, item, analysis):
    bonus = personal_relevance_bonus(db, item)
    overall_score, breakdown = compute_overall_score(analysis, item, personal_relevance_bonus=bonus)
    reason = build_reason(item, analysis, breakdown, overall_score)
    return overall_score, breakdown, reason


def _get_analyzed_items_with_analysis(db, extra_filter=None):
    query = {"analysis_status": "COMPLETED"}
    if extra_filter:
        query.update(extra_filter)
    items = list(db.instagram_items.find(query))
    results = []
    for item in items:
        analysis = db.ai_analyses.find_one({"_id": item.get("ai_analysis_id")}) if item.get("ai_analysis_id") else None
        if not analysis:
            continue
        results.append((item, analysis))
    return results


def recommend_general(db, limit=20):
    scored = []
    for item, analysis in _get_analyzed_items_with_analysis(db):
        overall_score, breakdown, reason = _score_item(db, item, analysis)
        scored.append({"item": item, "score": overall_score, "reason": reason})
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:limit]


def recommend_watch_next(db, limit=20):
    """WATCH_NEXT (section 17): items not yet watched, ranked by score."""
    scored = []
    for item, analysis in _get_analyzed_items_with_analysis(db, {"watch_count": 0}):
        overall_score, breakdown, reason = _score_item(db, item, analysis)
        scored.append({"item": item, "score": overall_score, "reason": reason})
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:limit]


def recommend_implement_next(db, limit=20):
    """
    IMPLEMENT_NEXT (section 18): items whose AI analysis suggests concrete
    actionable steps and has not already been applied, ranked by
    implementation_value_score-weighted overall score.
    """
    scored = []
    for item, analysis in _get_analyzed_items_with_analysis(db, {"status": {"$ne": "APPLIED"}}):
        if not analysis.get("actionable_steps"):
            continue
        overall_score, breakdown, reason = _score_item(db, item, analysis)
        suggested_action = analysis["actionable_steps"][0] if analysis.get("actionable_steps") else None
        scored.append({
            "item": item,
            "score": overall_score,
            "reason": reason,
            "suggested_action": suggested_action,
        })
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:limit]


def update_preference_from_feedback(db, topic, was_useful, step=0.1):
    """
    Adjust a topic's preference weight (section 15). Deliberately small,
    fixed step size and clamped to [0, 1] - simple and easy to reason about.
    """
    if not topic:
        return None
    pref = db.user_preferences.find_one({"topic": topic})
    current_weight = pref["weight"] if pref else DEFAULT_WEIGHT
    new_weight = current_weight + step if was_useful else current_weight - step
    new_weight = max(0.0, min(1.0, new_weight))

    from utils.dates import utcnow
    db.user_preferences.update_one(
        {"topic": topic},
        {"$set": {"weight": new_weight, "updated_at": utcnow()},
         "$setOnInsert": {"topic": topic, "created_at": utcnow()}},
        upsert=True,
    )
    return new_weight
