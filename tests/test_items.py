import pytest


def test_create_and_get_item(client):
    resp = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/ABC123/"}
    )
    assert resp.status_code == 201
    item = resp.get_json()["item"]
    assert item["status"] == "UNWATCHED"
    assert item["normalized_url"] == "https://instagram.com/reel/ABC123"

    resp = client.get(f"/api/items/{item['id']}")
    assert resp.status_code == 200
    assert resp.get_json()["item"]["id"] == item["id"]


def test_create_item_invalid_url(client):
    resp = client.post("/api/items", json={"url": "https://example.com/not-instagram"})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INVALID_INSTAGRAM_URL"


def test_create_item_duplicate(client):
    client.post("/api/items", json={"url": "https://www.instagram.com/reel/DUP1/"})
    resp = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/DUP1/"}
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "DUPLICATE_URL"


def test_get_item_invalid_id(client):
    resp = client.get("/api/items/not-an-id")
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INVALID_ITEM_ID"


def test_get_item_not_found(client):
    from bson import ObjectId

    resp = client.get(f"/api/items/{ObjectId()}")
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "ITEM_NOT_FOUND"


def test_update_item(client):
    item = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/UPD1/"}
    ).get_json()["item"]
    resp = client.patch(
        f"/api/items/{item['id']}", json={"status": "ARCHIVED", "priority": "HIGH"}
    )
    assert resp.status_code == 200
    updated = resp.get_json()["item"]
    assert updated["status"] == "ARCHIVED"
    assert updated["priority"] == "HIGH"


def test_update_item_invalid_status(client):
    item = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/UPD2/"}
    ).get_json()["item"]
    resp = client.patch(f"/api/items/{item['id']}", json={"status": "NOT_A_STATUS"})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INVALID_STATUS"


def test_delete_item(client):
    item = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/DEL1/"}
    ).get_json()["item"]
    resp = client.delete(f"/api/items/{item['id']}")
    assert resp.status_code == 200
    resp = client.get(f"/api/items/{item['id']}")
    assert resp.status_code == 404


def test_delete_item_removes_related_records(client, db):
    from bson import ObjectId

    item = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/DELRELATED1/"}
    ).get_json()["item"]
    item_id = ObjectId(item["id"])
    db.ai_jobs.insert_one({"item_id": item_id, "status": "QUEUED"})
    db.ai_analyses.insert_one({"item_id": item_id, "summary": "old"})
    db.actions.insert_one({"item_id": item_id, "title": "old action"})
    db.evidence.insert_one({"item_id": item_id, "frame_file_ids": []})

    response = client.delete(f"/api/items/{item['id']}")

    assert response.status_code == 200
    assert db.ai_jobs.count_documents({"item_id": item_id}) == 0
    assert db.ai_analyses.count_documents({"item_id": item_id}) == 0
    assert db.actions.count_documents({"item_id": item_id}) == 0
    assert db.evidence.count_documents({"item_id": item_id}) == 0


def test_delete_item_removes_exclusive_gridfs_evidence(client, db, monkeypatch):
    from bson import ObjectId
    from services.items import deletion

    item = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/DELEVIDENCE1/"}
    ).get_json()["item"]
    item_id = ObjectId(item["id"])
    video_id = ObjectId()
    deleted = []
    monkeypatch.setattr(deletion, "GridFSBucket", lambda db, bucket_name: bucket_name)
    monkeypatch.setattr(
        deletion, "_delete_gridfs_files", lambda bucket, ids: deleted.extend(ids)
    )
    db.evidence.insert_one(
        {"item_id": item_id, "video_file_id": video_id, "frame_file_ids": []}
    )

    assert client.delete(f"/api/items/{item['id']}").status_code == 200
    assert deleted == [video_id]


def test_delete_item_keeps_shared_gridfs_evidence(client, db, monkeypatch):
    from bson import ObjectId
    from services.items import deletion

    first = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/SHARED1/"}
    ).get_json()["item"]
    second = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/SHARED2/"}
    ).get_json()["item"]
    video_id = ObjectId()
    deleted = []
    monkeypatch.setattr(deletion, "GridFSBucket", lambda db, bucket_name: bucket_name)
    monkeypatch.setattr(
        deletion, "_delete_gridfs_files", lambda bucket, ids: deleted.extend(ids)
    )
    db.evidence.insert_many(
        [
            {
                "item_id": ObjectId(first["id"]),
                "video_file_id": video_id,
                "frame_file_ids": [],
            },
            {
                "item_id": ObjectId(second["id"]),
                "video_file_id": video_id,
                "frame_file_ids": [],
            },
        ]
    )

    assert client.delete(f"/api/items/{first['id']}").status_code == 200
    assert deleted == []


def test_toggle_useful_is_independent_of_analysis_score(client):
    item = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/USEFUL1/"}
    ).get_json()["item"]

    response = client.post(f"/api/items/{item['id']}/useful", json={"is_useful": True})

    assert response.status_code == 200
    assert response.get_json()["item"]["is_useful"] is True

    listed = client.get("/api/items?useful=true").get_json()
    assert listed["pagination"]["total"] == 1
    assert listed["items"][0]["id"] == item["id"]


def test_library_searches_tags_category_and_technical_topic(client, db):
    item = client.post(
        "/api/items",
        json={
            "url": "https://www.instagram.com/reel/SEARCHALL1/",
            "category": "Backend",
            "tags": ["Python", "Flask"],
        },
    ).get_json()["item"]
    from bson import ObjectId

    db.instagram_items.update_one(
        {"_id": ObjectId(item["id"])}, {"$set": {"technical_topic": "MongoDB indexes"}}
    )

    for term in ("Python", "Backend", "MongoDB"):
        response = client.get(f"/api/items?search={term}")
        assert response.status_code == 200
        assert response.get_json()["pagination"]["total"] == 1


def test_list_items_filter_by_status(client):
    client.post("/api/items", json={"url": "https://www.instagram.com/reel/LIST1/"})
    resp = client.get("/api/items?status=UNWATCHED")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["pagination"]["total"] >= 1
    assert all(item["status"] == "UNWATCHED" for item in body["items"])


def test_list_items_rejects_invalid_analysis_status(client):
    response = client.get("/api/items?analysis_status=NOT_A_REAL_STATUS")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_QUERY_PARAM"


def test_list_items_supports_oldest_sort(client, db):
    first = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/OLDEST1/"}
    ).get_json()["item"]
    second = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/OLDEST2/"}
    ).get_json()["item"]

    from bson import ObjectId
    from datetime import datetime, timedelta, timezone

    db.instagram_items.update_one(
        {"_id": ObjectId(first["id"])},
        {"$set": {"created_at": datetime.now(timezone.utc) - timedelta(days=2)}},
    )

    response = client.get("/api/items?sort=oldest&page_size=10")

    assert response.status_code == 200
    ids = [item["id"] for item in response.get_json()["items"]]
    assert ids.index(first["id"]) < ids.index(second["id"])


def test_watch_item(client):
    item = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/WATCH1/"}
    ).get_json()["item"]
    resp = client.post(f"/api/items/{item['id']}/watch")
    assert resp.status_code == 200
    updated = resp.get_json()["item"]
    assert updated["watch_count"] == 1
    assert updated["watched_at"] is not None
    assert updated["status"] == "WATCHED"

    resp2 = client.post(f"/api/items/{item['id']}/watch")
    assert resp2.get_json()["item"]["watch_count"] == 2


def test_apply_item_creates_action(client):
    item = client.post(
        "/api/items", json={"url": "https://www.instagram.com/reel/APPLY1/"}
    ).get_json()["item"]
    resp = client.post(
        f"/api/items/{item['id']}/apply",
        json={
            "create_action": True,
            "action_title": "Do the thing",
            "implementation_notes": "notes here",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["item"]["status"] == "APPLIED"
    assert body["created_action_id"] is not None

    resp2 = client.get(f"/api/actions/{body['created_action_id']}")
    assert resp2.status_code == 200
    assert resp2.get_json()["action"]["title"] == "Do the thing"
