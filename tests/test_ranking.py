from services.ai.ranking import compute_overall_score


def _analysis(**overrides):
    base = {
        "development_relevance_score": 80,
        "implementation_value_score": 80,
        "practicality_score": 80,
        "learning_value_score": 80,
        "originality_score": 80,
    }
    base.update(overrides)
    return base


def test_compute_overall_score_basic():
    item = {"watch_count": 0, "status": "UNWATCHED"}
    score, breakdown = compute_overall_score(_analysis(), item)
    assert score == 80
    assert breakdown["already_watched_penalty"] == 0
    assert breakdown["already_applied_penalty"] == 0


def test_compute_overall_score_applies_watched_penalty():
    item = {"watch_count": 2, "status": "WATCHED"}
    score, breakdown = compute_overall_score(_analysis(), item)
    assert breakdown["already_watched_penalty"] == -5
    assert score == 75


def test_compute_overall_score_applies_applied_penalty():
    item = {"watch_count": 1, "status": "APPLIED"}
    score, breakdown = compute_overall_score(_analysis(), item)
    assert breakdown["already_applied_penalty"] == -15
    assert score == 60  # 80 - 5 (watched) - 15 (applied)


def test_compute_overall_score_is_deterministic():
    item = {"watch_count": 0, "status": "UNWATCHED"}
    score1, _ = compute_overall_score(_analysis(development_relevance_score=50), item)
    score2, _ = compute_overall_score(_analysis(development_relevance_score=50), item)
    assert score1 == score2


def test_compute_overall_score_clamped_to_range():
    item = {"watch_count": 0, "status": "UNWATCHED"}
    score, _ = compute_overall_score(_analysis(
        development_relevance_score=0, implementation_value_score=0,
        practicality_score=0, learning_value_score=0, originality_score=0,
    ), item)
    assert 0 <= score <= 100


def test_personal_relevance_bonus_included():
    item = {"watch_count": 0, "status": "UNWATCHED"}
    score_no_bonus, _ = compute_overall_score(_analysis(), item, personal_relevance_bonus=0)
    score_with_bonus, _ = compute_overall_score(_analysis(), item, personal_relevance_bonus=10)
    assert score_with_bonus == score_no_bonus + 10
