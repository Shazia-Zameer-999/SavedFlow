"""
Similar/duplicate content detection (section 20).

V1 uses a simple, explainable overlap heuristic on AI-extracted concepts
(technical_concepts + dev_tricks + tools_mentioned) rather than a vector
database - explicitly acceptable per the spec ("do not over-engineer
vector databases unless necessary"). The similarity score and matched
concepts are stored so a future embedding-based approach could replace
just the scoring function without changing storage shape.
"""


def _concept_set(analysis):
    fields = ["technical_concepts", "dev_tricks", "tools_mentioned", "technologies_mentioned"]
    concepts = set()
    for field in fields:
        for value in analysis.get(field, []) or []:
            if isinstance(value, str):
                concepts.add(value.strip().lower())
    return concepts


def jaccard_similarity(analysis_a, analysis_b):
    set_a, set_b = _concept_set(analysis_a), _concept_set(analysis_b)
    if not set_a or not set_b:
        return 0.0, []
    intersection = set_a & set_b
    union = set_a | set_b
    score = len(intersection) / len(union) if union else 0.0
    return round(score, 3), sorted(intersection)


def find_similar_items(db, item_id, threshold=0.3, limit=10):
    """
    Find items whose AI analysis shares a meaningful fraction of
    technical concepts with the given item.
    """
    target_item = db.instagram_items.find_one({"_id": item_id})
    if not target_item or not target_item.get("ai_analysis_id"):
        return []
    target_analysis = db.ai_analyses.find_one({"_id": target_item["ai_analysis_id"]})
    if not target_analysis:
        return []

    candidates = db.instagram_items.find({
        "_id": {"$ne": item_id},
        "analysis_status": "COMPLETED",
    })

    similar = []
    for candidate in candidates:
        if not candidate.get("ai_analysis_id"):
            continue
        candidate_analysis = db.ai_analyses.find_one({"_id": candidate["ai_analysis_id"]})
        if not candidate_analysis:
            continue
        score, matched_concepts = jaccard_similarity(target_analysis, candidate_analysis)
        if score >= threshold:
            similar.append({
                "item_id": str(candidate["_id"]),
                "similarity_score": score,
                "matched_concepts": matched_concepts,
                "caption": candidate.get("caption"),
            })

    similar.sort(key=lambda x: x["similarity_score"], reverse=True)
    return similar[:limit]
