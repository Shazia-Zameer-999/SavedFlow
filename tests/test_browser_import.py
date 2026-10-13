import json

from bson import ObjectId
from services.ai.client import AIClient
from services.jobs.manager import create_job
from pathlib import Path

from services.ai import analyzer
from services.media.evidence_store import store_evidence


def test_local_browser_sync_imports_ten_distinct_posts(client):
    entries = [
        {"url": f"https://www.instagram.com/reel/POST{i:02d}/"} for i in range(10)
    ]
    response = client.post(
        "/api/instagram/sync",
        json={"source": "local_playwright", "status": "COMPLETED", "items": entries},
        headers={"X-SavedFlow-Sync-Token": "test-sync-token"},
    )
    body = response.get_json()
    assert body["imported"] == 10
    assert body["duplicates"] == 0
    assert (
        client.get("/api/items?page_size=100").get_json()["pagination"]["total"] == 10
    )


def test_local_browser_sync_does_not_queue_ai_analysis(client, db):
    payload = {
        "source": "local_playwright",
        "status": "COMPLETED",
        "items": [{"url": "https://www.instagram.com/reel/QUEUE1/"}],
    }

    response = client.post(
        "/api/instagram/sync",
        json=payload,
        headers={"X-SavedFlow-Sync-Token": "test-sync-token"},
    )

    assert response.get_json()["imported"] == 1

    item = db.instagram_items.find_one()
    assert item["analysis_status"] == "NOT_ANALYZED"
    assert db.ai_jobs.count_documents({}) == 0


def test_local_browser_sync_is_idempotent(client):
    payload = {
        "source": "local_playwright",
        "status": "COMPLETED",
        "items": [
            {"url": "https://www.instagram.com/reel/LOCAL1/"},
            {"url": "https://www.instagram.com/reel/LOCAL1/"},
        ],
    }
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


def test_deleted_item_is_not_reimported_by_later_browser_sync(client):
    payload = {
        "source": "local_playwright",
        "status": "COMPLETED",
        "items": [{"url": "https://www.instagram.com/reel/DELETEDSYNC1/"}],
    }
    item = client.post(
        "/api/instagram/sync",
        json=payload,
        headers={"X-SavedFlow-Sync-Token": "test-sync-token"},
    ).get_json()
    assert item["imported"] == 1

    saved_item = client.get("/api/items?page_size=10").get_json()["items"][0]
    assert client.delete(f"/api/items/{saved_item['id']}").status_code == 200

    repeated = client.post(
        "/api/instagram/sync",
        json=payload,
        headers={"X-SavedFlow-Sync-Token": "test-sync-token"},
    ).get_json()

    assert repeated["imported"] == 0
    assert repeated["skipped_deleted"] == 1
    assert client.get("/api/items?page_size=10").get_json()["pagination"]["total"] == 0


def test_ai_worker_requires_worker_token(client):
    response = client.post("/api/ai/worker/run")

    assert response.status_code == 401


def test_explicit_analysis_deduplicates_pending_jobs(client, db):
    item = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/ONEJOB1/"}
    ).get_json()["item"]
    first = client.post(f"/api/items/{item['id']}/analyze").get_json()["job"]
    second = client.post(f"/api/items/{item['id']}/analyze").get_json()["job"]
    assert first["id"] == second["id"]
    assert db.ai_jobs.count_documents({"item_id": ObjectId(item["id"])}) == 1


def test_atomic_job_claim_only_returns_one_claim(db):
    from services.jobs.manager import claim_next_job

    item_id = ObjectId()
    job_id = create_job(db, item_id)
    claimed = claim_next_job(db)
    assert claimed["_id"] == job_id
    assert claimed["status"] == "PROCESSING"
    assert claim_next_job(db) is None


def test_local_browser_sync_stops_on_auth_challenge(client):
    response = client.post(
        "/api/instagram/sync",
        json={"source": "local_playwright", "status": "LOGIN_CHALLENGE", "items": []},
        headers={"X-SavedFlow-Sync-Token": "test-sync-token"},
    )
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

    item_id = db.instagram_items.find_one({"_id": ObjectId(item["id"])})["_id"]

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
        "technical_topic": "Flask debugging",
        "implementation": {
            "can_implement": True,
            "steps": ["Add a breakpoint"],
            "required_tools": ["Python"],
            "estimated_effort": "LOW",
            "reason": "Simple debugging technique.",
        },
        "evidence_used": [],
        "transcript_relevance": "NOT_AVAILABLE",
        "transcript_reason": "",
        "content_creation": [],
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

    updated_item = client.get(f"/api/items/{item['id']}").get_json()["item"]

    assert updated_item["analysis_status"] == "COMPLETED"


def test_local_browser_sync_rejects_other_sources(client):
    response = client.post(
        "/api/instagram/sync",
        json={"source": "instagram_private_api", "items": []},
        headers={"X-SavedFlow-Sync-Token": "test-sync-token"},
    )
    assert response.status_code == 400


def test_browser_import_cleans_markdown_thumbnail_url(db):
    from services.instagram.browser_importer import LocalBrowserImporter

    thumbnail_url = "[https://example.com/image.jpg]" "(https://example.com/image.jpg)"

    importer = LocalBrowserImporter(db)

    result = importer.run(
        [
            {
                "url": "https://www.instagram.com/reel/THUMB1/",
                "thumbnail_url": thumbnail_url,
                "visible_label": "Test Reel",
            }
        ]
    )

    assert result.imported == 1

    item = db.instagram_items.find_one(
        {"normalized_url": "https://instagram.com/reel/THUMB1"}
    )

    assert item is not None

    assert item["source_metadata"]["thumbnail_url"] == "https://example.com/image.jpg"


def test_browser_import_cleans_image_markdown_and_strips_noise(db):
    from services.instagram.browser_importer import LocalBrowserImporter

    importer = LocalBrowserImporter(db)

    result = importer.run(
        [
            {
                "url": "https://www.instagram.com/reel/THUMB2/",
                "thumbnail_url": " ![Preview](https://example.com/preview.jpg) ",
                "visible_label": "Noise test",
            }
        ]
    )

    assert result.imported == 1

    item = db.instagram_items.find_one(
        {"normalized_url": "https://instagram.com/reel/THUMB2"}
    )
    assert item["source_metadata"]["thumbnail_url"] == "https://example.com/preview.jpg"


def test_default_gemini_model_uses_supported_release_name():
    from config import Config

    assert Config.GEMINI_MODEL == "gemini-2.5-flash"


def test_thumbnail_endpoint_streams_gridfs_thumbnail(client, db, tmp_path):
    from services.media.thumbnail_store import store_thumbnail

    image_path = tmp_path / "preview.jpg"
    image_path.write_bytes(b"fake-jpeg")
    file_id = store_thumbnail(db, image_path)

    response = client.get(f"/api/thumbnails/{file_id}")

    assert response.status_code == 200
    assert response.data == b"fake-jpeg"
    assert response.content_type == "image/jpeg"


def test_thumbnail_endpoint_rejects_missing_gridfs_thumbnail(client):
    response = client.get(f"/api/thumbnails/{ObjectId()}")

    assert response.status_code == 404


def test_evidence_gridfs_round_trip_includes_video_and_frames(db, tmp_path):
    from services.media.evidence_store import (
        download_evidence_frames,
        download_evidence_video,
        store_evidence,
    )

    video_path = tmp_path / "reel.webm"
    frame_path = tmp_path / "frame-1.jpg"
    video_path.write_bytes(b"video-bytes")
    frame_path.write_bytes(b"frame-bytes")

    evidence = store_evidence(
        db,
        {
            "video_path": video_path,
            "duration": 2.0,
            "frames": [frame_path],
            "transcript": "spoken words",
            "transcript_source": "WHISPER",
        },
    )
    output_video = tmp_path / "downloaded.webm"
    download_evidence_video(db, evidence, output_video)
    frame_paths = download_evidence_frames(db, evidence, tmp_path / "downloaded-frames")

    assert output_video.read_bytes() == b"video-bytes"
    assert len(frame_paths) == 1
    assert Path(frame_paths[0]).read_bytes() == b"frame-bytes"


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
        "items": [
            {
                "url": "https://www.instagram.com/p/Preview1/",
                "thumbnail_url": "https://cdninstagram.example/preview.jpg",
                "visible_label": "A visible Instagram card label",
            }
        ],
    }
    assert (
        client.post(
            "/api/instagram/sync",
            json=payload,
            headers={"X-SavedFlow-Sync-Token": "test-sync-token"},
        ).get_json()["imported"]
        == 1
    )
    item = client.get("/api/items?page_size=10").get_json()["items"][0]
    assert item["source_metadata"]["thumbnail_url"].endswith("preview.jpg")
    assert item["source_metadata"]["visible_label"] == "A visible Instagram card label"


def test_ai_worker_uses_stored_evidence_video(
    client,
    db,
    monkeypatch,
):
    item = client.post(
        "/api/items",
        json={
            "url": "https://www.instagram.com/reel/GRIDFS1/",
            "caption": "GridFS evidence test",
        },
    ).get_json()["item"]

    item_id = ObjectId(item["id"])

    create_job(db, item_id)

    fake_video_content = b"fake-video-data"

    fake_evidence = {
        "_id": ObjectId(),
        "item_id": item_id,
        "video_file_id": ObjectId(),
        "duration": 5.0,
        "transcript": "Stored transcript from Whisper.",
        "transcript_source": "WHISPER",
    }

    temporary_paths = {}

    def fake_get_evidence_for_item(db, item_id):
        assert item_id == ObjectId(item["id"])
        return fake_evidence

    def fake_download_evidence_video(
        db,
        evidence,
        output_path,
    ):
        assert evidence["_id"] == fake_evidence["_id"]

        path = Path(output_path)
        path.write_bytes(fake_video_content)

        temporary_paths["path"] = path

        return str(path)

    def fake_analyze_item(item, ai_client=None, evidence=None):
        video_path = item.get("local_video_path")

        assert video_path is not None
        assert Path(video_path).exists()
        assert Path(video_path).read_bytes() == fake_video_content

        assert evidence is not None
        assert evidence["transcript"] == "Stored transcript from Whisper."
        assert evidence["transcript_source"] == "WHISPER"

        return (
            "VIDEO",
            {
                "summary": "GridFS test.",
                "technical_topic": "Testing",
                "core_idea": "Test stored evidence.",
                "problem_solved": "Testing evidence retrieval.",
                "key_takeaways": [],
                "dev_tricks": [],
                "technical_concepts": [],
                "tools_mentioned": [],
                "technologies_mentioned": [],
                "libraries_mentioned": [],
                "actionable_steps": [],
                "implementation": {
                    "can_implement": True,
                    "steps": [],
                    "required_tools": [],
                    "estimated_effort": "LOW",
                    "reason": "Test.",
                },
                "difficulty": "BEGINNER",
                "practicality_score": 80,
                "learning_value_score": 80,
                "implementation_value_score": 80,
                "development_relevance_score": 80,
                "originality_score": 50,
                "overall_usefulness_score": 80,
                "why_useful": "Test.",
                "who_should_use_it": "Developers.",
                "potential_limitations": [],
                "claims_to_verify": [],
                "recommendation": "WATCH_NOW",
                "confidence": 90,
                "evidence_used": [],
                "transcript_relevance": "RELEVANT",
                "transcript_reason": "Test transcript.",
                "content_creation": [],
            },
        )

    monkeypatch.setattr(
        "services.jobs.manager.get_evidence_for_item",
        fake_get_evidence_for_item,
    )

    monkeypatch.setattr(
        "services.jobs.manager.download_evidence_video",
        fake_download_evidence_video,
    )

    monkeypatch.setattr(
        "services.jobs.manager.analyze_item",
        fake_analyze_item,
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

    assert "path" in temporary_paths

    # The worker must clean up the temporary video.
    assert not temporary_paths["path"].exists()
