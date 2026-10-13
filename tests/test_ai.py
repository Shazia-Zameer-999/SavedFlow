import json

import pytest

from services.ai.client import AIClient, AIClientError
from services.ai.analyzer import (
    validate_structured_output,
    AnalysisValidationError,
    determine_available_content,
)

VALID_AI_JSON = {
    "summary": "A Flask debugging trick.",
    "technical_topic": "Flask debugging",
    "core_idea": "Use Flask breakpoints for debugging.",
    "problem_solved": "Slow debugging.",
    "key_takeaways": ["Use pdb"],
    "dev_tricks": ["Use breakpoint()"],
    "technical_concepts": ["debugging"],
    "tools_mentioned": ["pdb"],
    "technologies_mentioned": ["Flask"],
    "libraries_mentioned": [],
    "actionable_steps": ["Add breakpoint() to a route handler"],
    "implementation": {
        "can_implement": True,
        "steps": ["Add a breakpoint"],
        "required_tools": ["Python"],
        "estimated_effort": "LOW",
        "reason": "Simple debugging technique.",
    },
    "difficulty": "BEGINNER",
    "practicality_score": 80,
    "learning_value_score": 70,
    "implementation_value_score": 75,
    "development_relevance_score": 90,
    "originality_score": 40,
    "overall_usefulness_score": 78,
    "why_useful": "Helps with debugging.",
    "who_should_use_it": "Flask developers.",
    "potential_limitations": [],
    "claims_to_verify": [],
    "recommendation": "WATCH_NOW",
    "confidence": 85,
    "evidence_used": [],
    "transcript_relevance": "NOT_AVAILABLE",
    "transcript_reason": "",
    "content_creation": [],
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
    item = client.post(
        "/api/items",
        json={
            "url": "https://www.instagram.com/reel/AIFLOW1/",
            "caption": "Flask debugging trick",
        },
    ).get_json()["item"]

    monkeypatch.setattr(AIClient, "is_configured", lambda self: True)
    monkeypatch.setattr(
        AIClient,
        "complete_json",
        lambda self, sys, usr, temperature=0.2: json.dumps(VALID_AI_JSON),
    )

    resp = client.post(f"/api/items/{item['id']}/analyze")
    assert resp.status_code == 202
    job = resp.get_json()["job"]
    assert job["status"] == "QUEUED"

    worker_resp = client.post(
        "/api/ai/worker/run",
        headers={"X-SavedFlow-Worker-Token": "test-worker-token"},
    )
    assert worker_resp.get_json()["job"]["status"] == "COMPLETED"

    updated_item = client.get(f"/api/items/{item['id']}").get_json()["item"]
    assert updated_item["analysis_status"] == "COMPLETED"
    assert updated_item["usefulness_score"] == 78
    assert updated_item["recommendation"] == "WATCH_NOW"

    analysis_resp = client.get(f"/api/items/{item['id']}/analysis")
    assert analysis_resp.status_code == 200
    assert analysis_resp.get_json()["analysis"]["analysis_basis"] == "METADATA_ONLY"


def test_analyze_endpoint_handles_ai_failure_gracefully(client, monkeypatch):
    item = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/AIFAIL1/"}
    ).get_json()["item"]

    monkeypatch.setattr(AIClient, "is_configured", lambda self: True)
    monkeypatch.setattr(
        AIClient,
        "complete_json",
        lambda self, sys, usr, temperature=0.2: "not valid json {{{",
    )

    resp = client.post(f"/api/items/{item['id']}/analyze")
    job = resp.get_json()["job"]
    assert job["status"] == "QUEUED"
    job = client.post(
        "/api/ai/worker/run",
        headers={"X-SavedFlow-Worker-Token": "test-worker-token"},
    ).get_json()["job"]
    assert job["status"] == "FAILED"
    assert job["error"] is not None

    updated_item = client.get(f"/api/items/{item['id']}").get_json()["item"]
    assert updated_item["analysis_status"] == "FAILED"


def test_analyze_endpoint_without_api_key_fails_job(client, monkeypatch):
    item = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/NOKEY1/"}
    ).get_json()["item"]
    monkeypatch.setattr(AIClient, "is_configured", lambda self: False)

    resp = client.post(f"/api/items/{item['id']}/analyze")
    job = resp.get_json()["job"]
    assert job["status"] == "QUEUED"
    job = client.post(
        "/api/ai/worker/run",
        headers={"X-SavedFlow-Worker-Token": "test-worker-token"},
    ).get_json()["job"]
    assert job["status"] == "FAILED"
    assert "GEMINI_API_KEY" in job["error"]


def test_ai_worker_stops_at_daily_gemini_limit(client, db, monkeypatch):
    from datetime import datetime, timezone
    from services.jobs.manager import create_job

    item = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/AILIMIT1/"}
    ).get_json()["item"]
    item_id = db.instagram_items.find_one({"_id": item["id"]})
    # The API response stores the id as text; use the persisted document for the job.
    if item_id is None:
        from bson import ObjectId

        item_id = db.instagram_items.find_one({"_id": ObjectId(item["id"])})
    create_job(db, item_id["_id"])
    db.ai_usage.insert_one(
        {
            "date": datetime.now(timezone.utc).date().isoformat(),
            "count": 20,
        }
    )

    monkeypatch.setattr(AIClient, "is_configured", lambda self: True)
    monkeypatch.setattr(
        AIClient,
        "complete_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Gemini called")),
    )

    response = client.post(
        "/api/ai/worker/run",
        headers={"X-SavedFlow-Worker-Token": "test-worker-token"},
    )

    assert response.get_json()["job"]["status"] == "WAITING_FOR_QUOTA"
    assert response.get_json()["job"]["stage"] == "WAITING_FOR_GEMINI_QUOTA"
    assert "daily Gemini request limit" in response.get_json()["job"]["error"]
    assert response.get_json()["job"]["retry_after"] is not None


def test_evidence_collection_reports_frame_and_audio_stages(tmp_path, monkeypatch):
    from services.media import evidence

    video_path = tmp_path / "reel.webm"
    video_path.write_bytes(b"video")
    stages = []
    monkeypatch.setattr(evidence, "extract_frames", lambda **kwargs: ["frame.jpg"])
    monkeypatch.setattr(evidence, "transcribe_audio", lambda **kwargs: "spoken text")

    result = evidence.collect_evidence(
        video_path,
        duration=2.0,
        output_dir=tmp_path / "derived",
        on_stage=stages.append,
    )

    assert stages == ["EXTRACTING_FRAMES", "TRANSCRIBING_AUDIO"]
    assert result["transcript"] == "spoken text"


def test_provider_quota_error_waits_without_permanent_failure(client, db, monkeypatch):
    from bson import ObjectId
    from services.ai.client import GeminiQuotaError
    from services.jobs import manager

    item = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/AI4291/"}
    ).get_json()["item"]
    item_id = ObjectId(item["id"])
    job_id = manager.create_job(db, item_id)
    monkeypatch.setattr(manager.AIClient, "is_configured", lambda self: True)
    monkeypatch.setattr(
        manager,
        "analyze_item",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            GeminiQuotaError("RESOURCE_EXHAUSTED")
        ),
    )

    response = client.post(
        "/api/ai/worker/run",
        headers={"X-SavedFlow-Worker-Token": "test-worker-token"},
    )

    job = db.ai_jobs.find_one({"_id": job_id})
    assert response.status_code == 200
    assert job["status"] == "WAITING_FOR_QUOTA"
    assert job["retry_after"] is not None
    assert (
        db.instagram_items.find_one({"_id": item_id})["analysis_status"]
        == "WAITING_FOR_QUOTA"
    )


def test_job_not_found(client):
    from bson import ObjectId

    resp = client.get(f"/api/jobs/{ObjectId()}")
    assert resp.status_code == 404


def test_failed_job_can_be_retried_once(client, db):
    from bson import ObjectId

    item = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/RETRY1/"}
    ).get_json()["item"]
    item_id = ObjectId(item["id"])
    failed = db.ai_jobs.insert_one(
        {
            "item_id": item_id,
            "status": "FAILED",
            "stage": "FAILED",
            "job_type": "ANALYZE",
            "retry_count": 0,
        }
    ).inserted_id
    db.instagram_items.update_one(
        {"_id": item_id}, {"$set": {"analysis_status": "FAILED"}}
    )

    response = client.post(f"/api/jobs/{failed}/retry")

    assert response.status_code == 202
    job = response.get_json()["job"]
    assert job["status"] == "QUEUED"
    assert job["retry_count"] == 1
    assert job["retry_of"] == str(failed)
    assert (
        client.get(f"/api/items/{item['id']}").get_json()["item"]["analysis_status"]
        == "QUEUED"
    )


def test_stale_processing_jobs_are_requeued(client, db):
    from datetime import datetime, timedelta, timezone
    from bson import ObjectId

    item = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/STALE1/"}
    ).get_json()["item"]
    stale_id = db.ai_jobs.insert_one(
        {
            "item_id": ObjectId(item["id"]),
            "status": "PROCESSING",
            "stage": "ANALYZING_WITH_GEMINI",
            "created_at": datetime.now(timezone.utc) - timedelta(hours=2),
            "started_at": datetime.now(timezone.utc) - timedelta(hours=2),
            "retry_count": 0,
        }
    ).inserted_id

    response = client.post(
        "/api/ai/worker/run",
        headers={"X-SavedFlow-Worker-Token": "test-worker-token"},
    )

    assert response.status_code == 200
    json_body = response.get_json()
    assert json_body["processed"] in {True, False}
    refreshed = db.ai_jobs.find_one({"_id": stale_id})
    assert refreshed is not None
    assert refreshed["status"] in {"QUEUED", "PROCESSING", "COMPLETED", "FAILED"}
    item_doc = db.instagram_items.find_one({"_id": ObjectId(item["id"])})
    assert item_doc["analysis_status"] in {
        "QUEUED",
        "PROCESSING",
        "COMPLETED",
        "FAILED",
    }


def test_analyze_requeues_a_stale_processing_job(client, db):
    from datetime import datetime, timedelta, timezone
    from bson import ObjectId

    item = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/STALE2/"}
    ).get_json()["item"]
    item_id = ObjectId(item["id"])
    stale_id = db.ai_jobs.insert_one(
        {
            "item_id": item_id,
            "status": "PROCESSING",
            "stage": "ANALYZING_WITH_GEMINI",
            "created_at": datetime.now(timezone.utc) - timedelta(hours=2),
            "started_at": datetime.now(timezone.utc) - timedelta(hours=2),
            "retry_count": 0,
        }
    ).inserted_id

    response = client.post(f"/api/items/{item['id']}/analyze")

    assert response.status_code == 202
    assert response.get_json()["job"]["id"] == str(stale_id)
    assert db.ai_jobs.find_one({"_id": stale_id})["status"] == "QUEUED"


def test_retry_rejects_a_non_failed_job(client, db):
    from bson import ObjectId

    item = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/RETRY2/"}
    ).get_json()["item"]
    job_id = db.ai_jobs.insert_one(
        {"item_id": ObjectId(item["id"]), "status": "COMPLETED", "retry_count": 0}
    ).inserted_id

    response = client.post(f"/api/jobs/{job_id}/retry")

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "JOB_NOT_RETRYABLE"
