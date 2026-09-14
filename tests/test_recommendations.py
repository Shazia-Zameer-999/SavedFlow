from utils.dates import utcnow


def _make_analyzed_item(db, url_suffix, scores, category=None, watch_count=0, status="UNWATCHED", recommendation=None, actionable_steps=None):
    from models.item import new_item
    from models.analysis import new_analysis
    from utils.urls import normalize_instagram_url

    url = f"https://www.instagram.com/reel/{url_suffix}/"
    item = new_item(url=url, normalized_url=normalize_instagram_url(url), source_method="MANUAL")
    item["watch_count"] = watch_count
    item["status"] = status
    item["analysis_status"] = "COMPLETED"
    item["category"] = category
    item["recommendation"] = recommendation
    inserted_item = db.instagram_items.insert_one(item)

    analysis = new_analysis(
        item_id=inserted_item.inserted_id,
        structured_output={
            "summary": "s", "core_idea": "c", "problem_solved": "p",
            "key_takeaways": [], "dev_tricks": [], "technical_concepts": [],
            "tools_mentioned": [], "technologies_mentioned": [], "libraries_mentioned": [],
            "actionable_steps": actionable_steps or [],
            "difficulty": "BEGINNER", "why_useful": "w", "who_should_use_it": "w",
            "potential_limitations": [], "claims_to_verify": [],
            "recommendation": recommendation or "WATCH_NOW", "confidence": 80,
            **scores,
        },
        analysis_basis="METADATA_ONLY",
        model="test-model",
    )
    inserted_analysis = db.ai_analyses.insert_one(analysis)
    db.instagram_items.update_one(
        {"_id": inserted_item.inserted_id},
        {"$set": {"ai_analysis_id": inserted_analysis.inserted_id, "usefulness_score": scores["overall_usefulness_score"]}},
    )
    return inserted_item.inserted_id


HIGH_SCORES = dict(
    development_relevance_score=90, implementation_value_score=90,
    practicality_score=90, learning_value_score=90, originality_score=90,
    overall_usefulness_score=90,
)
LOW_SCORES = dict(
    development_relevance_score=20, implementation_value_score=20,
    practicality_score=20, learning_value_score=20, originality_score=20,
    overall_usefulness_score=20,
)


def test_recommendations_general_ranks_by_score(client, db):
    _make_analyzed_item(db, "REC_LOW", LOW_SCORES)
    _make_analyzed_item(db, "REC_HIGH", HIGH_SCORES)

    resp = client.get("/api/recommendations")
    assert resp.status_code == 200
    recs = resp.get_json()["recommendations"]
    assert len(recs) == 2
    assert recs[0]["score"] >= recs[1]["score"]
    assert "reason" in recs[0]


def test_recommendations_watch_excludes_watched_items(client, db):
    _make_analyzed_item(db, "WATCHNEXT1", HIGH_SCORES, watch_count=0)
    _make_analyzed_item(db, "WATCHNEXT2", HIGH_SCORES, watch_count=3)

    resp = client.get("/api/recommendations/watch")
    body = resp.get_json()
    assert body["category"] == "WATCH_NEXT"
    item_ids = [r["item_id"] for r in body["recommendations"]]
    assert len(item_ids) == 1


def test_recommendations_implement_requires_actionable_steps(client, db):
    _make_analyzed_item(db, "IMPL1", HIGH_SCORES, actionable_steps=["Do the thing"])
    _make_analyzed_item(db, "IMPL2", HIGH_SCORES, actionable_steps=[])

    resp = client.get("/api/recommendations/implement")
    body = resp.get_json()
    assert body["category"] == "IMPLEMENT_NEXT"
    assert len(body["recommendations"]) == 1
    assert body["recommendations"][0]["suggested_action"] == "Do the thing"


def test_recommendations_implement_excludes_applied(client, db):
    _make_analyzed_item(db, "IMPL3", HIGH_SCORES, actionable_steps=["Step"], status="APPLIED")
    resp = client.get("/api/recommendations/implement")
    assert resp.get_json()["recommendations"] == []


def test_preferences_update_and_bonus_affects_ranking(client, db):
    resp = client.patch("/api/preferences", json={"topic": "MongoDB", "was_useful": True})
    assert resp.status_code == 200
    weight_after_one = resp.get_json()["preference"]["weight"]
    assert weight_after_one > 0.5

    _make_analyzed_item(db, "PREF1", HIGH_SCORES, category="MongoDB")
    resp2 = client.get("/api/recommendations")
    assert resp2.status_code == 200
    assert resp2.get_json()["recommendations"][0]["score"] >= 90


def test_dashboard_reflects_real_data(client, db):
    _make_analyzed_item(db, "DASH1", HIGH_SCORES, recommendation="WATCH_NOW")
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total_items"] == 1
    assert body["ai_analyzed"] == 1
    assert body["worth_watching"] == 1


def test_weekly_review_uses_real_data_only(client, db):
    _make_analyzed_item(db, "WEEK1", HIGH_SCORES)
    resp = client.post("/api/weekly-review")
    assert resp.status_code == 201
    review = resp.get_json()["review"]
    assert "narrative_summary" in review
    assert review["items_imported"] >= 0

    resp2 = client.get(f"/api/weekly-review/{review['id']}")
    assert resp2.status_code == 200
    assert resp2.get_json()["review"]["id"] == review["id"]
