import json

import pytest

from services.ai.client import AIClient, AIClientError
from services.ai.analyzer import validate_structured_output, AnalysisValidationError, determine_available_content

VALID_AI_JSON = {
    "summary": "A quick trick for debugging Flask apps.",
    "core_idea": "Use Flask's debug mode with breakpoints.",
    "problem_solved": "Slow debugging via print statements.",
    "key_takeaways": ["Use pdb", "Enable debug mode"],
    "dev_tricks": ["Insert breakpoint() in Flask routes"],
    "technical_concepts": ["debugging", "Flask"],
    "tools_mentioned": ["pdb"],
    "technologies_mentioned": ["Flask"],
    "libraries_mentioned": [],
    "actionable_steps": ["Add breakpoint() to a route handler"],
    "difficulty": "BEGINNER",
    "practicality_score": 80,
    "learning_value_score": 70,
    "implementation_value_score": 75,
    "development_relevance_score": 90,
    "originality_score": 40,
    "overall_usefulness_score": 78,
    "why_useful": "Speeds up debugging.",
    "who_should_use_it": "Flask developers.",
    "potential_limitations": [],
    "claims_to_verify": [],
    "recommendation": "WATCH_NOW",
    "confidence": 85,
}


def test_validate_structured_output_accepts_valid_data():
    result = validate_structured_output(dict(VALID_AI_JSON))
    assert result["overall_usefulness_score"] == 78


def test_validate_structured_output_rejects_missing_field():
    bad = dict(VALID_AI_JSON)
    del bad["summary"]
    with pytest.raises(AnalysisValidationError):
        validate_structured_output(bad)


def test_validate_structured_output_rejects_out_of_range_score():
    bad = dict(VALID_AI_JSON)
    bad["confidence"] = 150
    with pytest.raises(AnalysisValidationError):
        validate_structured_output(bad)


def test_validate_structured_output_rejects_invalid_recommendation():
    bad = dict(VALID_AI_JSON)
    bad["recommendation"] = "MAYBE"
    with pytest.raises(AnalysisValidationError):
        validate_structured_output(bad)


def test_determine_available_content_metadata_only():
    item = {"caption": "A cool Flask trick"}
    available = determine_available_content(item)
    assert available["basis"] == "METADATA_ONLY"
    assert available["caption"] == "A cool Flask trick"


def test_determine_available_content_uses_transcript_when_present():
    item = {"caption": "cap", "transcript": "full transcript text"}
    available = determine_available_content(item)
    assert available["basis"] == "TRANSCRIPT"
    assert available["transcript"] == "full transcript text"


def test_ai_client_parse_json_valid():
    parsed = AIClient.parse_json(json.dumps(VALID_AI_JSON))
    assert parsed["summary"] == VALID_AI_JSON["summary"]


def test_ai_client_parse_json_repairs_markdown_fence():
    fenced = "```json\n" + json.dumps(VALID_AI_JSON) + "\n```"
    parsed = AIClient.parse_json(fenced)
    assert parsed["core_idea"] == VALID_AI_JSON["core_idea"]


def test_ai_client_parse_json_invalid_raises():
    with pytest.raises(AIClientError):
        AIClient.parse_json("not json at all {{{")


def test_ai_client_not_configured_raises(monkeypatch):
    client_instance = AIClient(api_key="")
    with pytest.raises(AIClientError):
        client_instance.complete_json("system", "user")


def test_analyze_endpoint_full_pipeline(client, monkeypatch):
    """
    End-to-end: create an item, mock the AI client's HTTP call, hit
    /analyze, and confirm the item + analysis were stored correctly.
    """
    item = client.post("/api/items", json={
        "url": "https://www.instagram.com/reel/AIFLOW1/",
        "caption": "Flask debugging trick",
    }).get_json()["item"]

    monkeypatch.setattr(AIClient, "is_configured", lambda self: True)
    monkeypatch.setattr(AIClient, "complete_json", lambda self, sys, usr, temperature=0.2: json.dumps(VALID_AI_JSON))

    resp = client.post(f"/api/items/{item['id']}/analyze")
    assert resp.status_code == 202
    job = resp.get_json()["job"]
    assert job["status"] == "COMPLETED"

    updated_item = client.get(f"/api/items/{item['id']}").get_json()["item"]
    assert updated_item["analysis_status"] == "COMPLETED"
    assert updated_item["usefulness_score"] == 78
    assert updated_item["recommendation"] == "WATCH_NOW"

    analysis_resp = client.get(f"/api/items/{item['id']}/analysis")
    assert analysis_resp.status_code == 200
    assert analysis_resp.get_json()["analysis"]["analysis_basis"] == "METADATA_ONLY"


def test_analyze_endpoint_handles_ai_failure_gracefully(client, monkeypatch):
    item = client.post("/api/items", json={"url": "https://www.instagram.com/reel/AIFAIL1/"}).get_json()["item"]

    monkeypatch.setattr(AIClient, "is_configured", lambda self: True)
    monkeypatch.setattr(AIClient, "complete_json", lambda self, sys, usr, temperature=0.2: "not valid json {{{")

    resp = client.post(f"/api/items/{item['id']}/analyze")
    job = resp.get_json()["job"]
    assert job["status"] == "FAILED"
    assert job["error"] is not None

    updated_item = client.get(f"/api/items/{item['id']}").get_json()["item"]
    assert updated_item["analysis_status"] == "FAILED"


def test_analyze_endpoint_without_api_key_fails_job(client, monkeypatch):
    item = client.post("/api/items", json={"url": "https://www.instagram.com/reel/NOKEY1/"}).get_json()["item"]
    monkeypatch.setattr(AIClient, "is_configured", lambda self: False)

    resp = client.post(f"/api/items/{item['id']}/analyze")
    job = resp.get_json()["job"]
    assert job["status"] == "FAILED"
    assert "GEMINI_API_KEY" in job["error"]


def test_job_not_found(client):
    from bson import ObjectId
    resp = client.get(f"/api/jobs/{ObjectId()}")
    assert resp.status_code == 404
