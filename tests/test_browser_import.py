import json

from bson import ObjectId
from services.ai.client import AIClient
from services.jobs.manager import create_job
def test_local_browser_sync_imports_ten_distinct_posts(client):
    entries = [{"url": f"https://www.instagram.com/reel/POST{i:02d}/"} for i in range(10)]
    response = client.post("/api/instagram/sync", json={
    "source": "local_playwright", "status": "COMPLETED", "items": entries
}, headers={"X-SavedFlow-Sync-Token": "test-sync-token"})
    body = response.get_json()
    assert body["imported"] == 10
    assert body["duplicates"] == 0
    assert client.get("/api/items?page_size=100").get_json()["pagination"]["total"] == 10

def test_local_browser_sync_queues_ai_analysis(client, db):
    payload = {
        "source": "local_playwright",
        "status": "COMPLETED",
        "items": [{
            "url": "https://www.instagram.com/reel/QUEUE1/"
        }],
    }

    response = client.post(
        "/api/instagram/sync",
        json=payload,
        headers={"X-SavedFlow-Sync-Token": "test-sync-token"},
    )

    assert response.get_json()["imported"] == 1

    item = db.instagram_items.find_one()
    assert item["analysis_status"] == "QUEUED"

    job = db.ai_jobs.find_one()
    assert job is not None
    assert job["item_id"] == item["_id"]
    assert job["status"] == "QUEUED"
    assert job["job_type"] == "ANALYZE"

def test_local_browser_sync_is_idempotent(client):
    payload = {"source": "local_playwright", "status": "COMPLETED", "items": [
        {"url": "https://www.instagram.com/reel/LOCAL1/"},
        {"url": "https://www.instagram.com/reel/LOCAL1/"},
    ]}
    first = client.post(
    "/api/instagram/sync",
    json=payload,
    headers={"X-SavedFlow-Sync-Token": "test-sync-token"},
).get_json()
    assert first["imported"] == 1 and first["duplicates"] == 1
    second = client.post(
    "/api/instagram/sync",
    json=payload,
    headers={"X-SavedFlow-Sync-Token": "test-sync-token"},
).get_json()
    assert second["imported"] == 0 and second["duplicates"] == 2

def test_ai_worker_requires_worker_token(client):
    response = client.post("/api/ai/worker/run")

    assert response.status_code == 401
def test_local_browser_sync_stops_on_auth_challenge(client):
    response = client.post("/api/instagram/sync", json={
        "source": "local_playwright",
        "status": "LOGIN_CHALLENGE",
        "items": []
    }, headers={"X-SavedFlow-Sync-Token": "test-sync-token"})
    assert response.status_code == 401

def test_ai_worker_returns_when_no_jobs_are_queued(client):
    response = client.post(
        "/api/ai/worker/run",
        headers={"X-SavedFlow-Worker-Token": "test-worker-token"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["processed"] is False
def test_ai_worker_processes_queued_job(client, db, monkeypatch):
    item = client.post(
        "/api/items",
        json={
            "url": "https://www.instagram.com/reel/WORKER1/",
            "caption": "Flask worker test",
        },
    ).get_json()["item"]

    item_id = db.instagram_items.find_one(
        {"_id": ObjectId(item["id"])}
    )["_id"]

    create_job(db, item_id)

    valid_ai_json = {
        "summary": "A Flask debugging trick.",
        "core_idea": "Use breakpoints for debugging.",
        "problem_solved": "Slow debugging.",
        "key_takeaways": ["Use pdb"],
        "dev_tricks": ["Use breakpoint()"],
        "technical_concepts": ["debugging"],
        "tools_mentioned": ["pdb"],
        "technologies_mentioned": ["Flask"],
        "libraries_mentioned": [],
        "actionable_steps": ["Add a breakpoint"],
        "difficulty": "BEGINNER",
        "practicality_score": 80,
        "learning_value_score": 70,
        "implementation_value_score": 75,
        "development_relevance_score": 90,
        "originality_score": 40,
        "overall_usefulness_score": 78,
        "why_useful": "Helps debugging.",
        "who_should_use_it": "Flask developers.",
        "potential_limitations": [],
        "claims_to_verify": [],
        "recommendation": "WATCH_NOW",
        "confidence": 85,
    }

    monkeypatch.setattr(AIClient, "is_configured", lambda self: True)
    monkeypatch.setattr(
        AIClient,
        "complete_json",
        lambda self, sys, usr, temperature=0.2: json.dumps(valid_ai_json),
    )

    response = client.post(
        "/api/ai/worker/run",
        headers={"X-SavedFlow-Worker-Token": "test-worker-token"},
    )

    assert response.status_code == 200

    body = response.get_json()
    assert body["success"] is True
    assert body["processed"] is True
    assert body["job"]["status"] == "COMPLETED"

    updated_item = client.get(
        f"/api/items/{item['id']}"
    ).get_json()["item"]

    assert updated_item["analysis_status"] == "COMPLETED"
def test_local_browser_sync_rejects_other_sources(client):
    response = client.post("/api/instagram/sync", json={
        "source": "instagram_private_api", "items": []
    },headers={"X-SavedFlow-Sync-Token": "test-sync-token"})
    assert response.status_code == 400


def test_startup_removes_legacy_unique_permalink_index(db):
    from extensions import _create_indexes

    db.instagram_items.create_index("permalink", unique=True)
    _create_indexes(db)
    names = {index["name"] for index in db.instagram_items.list_indexes()}
    assert "permalink_1" not in names


def test_local_browser_sync_stores_and_enriches_visible_metadata(client):
    payload = {
        "source": "local_playwright",
        "status": "COMPLETED",
        "items": [{
            "url": "https://www.instagram.com/p/Preview1/",
            "thumbnail_url": "https://cdninstagram.example/preview.jpg",
            "visible_label": "A visible Instagram card label",
        }],
    }
    assert client.post(
    "/api/instagram/sync",
    json=payload,
    headers={"X-SavedFlow-Sync-Token": "test-sync-token"},
).get_json()["imported"] == 1
    item = client.get("/api/items?page_size=10").get_json()["items"][0]
    assert item["source_metadata"]["thumbnail_url"].endswith("preview.jpg")
    assert item["source_metadata"]["visible_label"] == "A visible Instagram card label"
