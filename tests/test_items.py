def test_create_and_get_item(client):
    resp = client.post("/api/items", json={"url": "https://www.instagram.com/reel/ABC123/"})
    assert resp.status_code == 201
    item = resp.get_json()["item"]
    assert item["status"] == "NEW"
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
    resp = client.post("/api/items", json={"url": "https://www.instagram.com/reel/DUP1/"})
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
    item = client.post("/api/items", json={"url": "https://www.instagram.com/reel/UPD1/"}).get_json()["item"]
    resp = client.patch(f"/api/items/{item['id']}", json={"status": "ARCHIVED", "priority": "HIGH"})
    assert resp.status_code == 200
    updated = resp.get_json()["item"]
    assert updated["status"] == "ARCHIVED"
    assert updated["priority"] == "HIGH"


def test_update_item_invalid_status(client):
    item = client.post("/api/items", json={"url": "https://www.instagram.com/reel/UPD2/"}).get_json()["item"]
    resp = client.patch(f"/api/items/{item['id']}", json={"status": "NOT_A_STATUS"})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INVALID_STATUS"


def test_delete_item(client):
    item = client.post("/api/items", json={"url": "https://www.instagram.com/reel/DEL1/"}).get_json()["item"]
    resp = client.delete(f"/api/items/{item['id']}")
    assert resp.status_code == 200
    resp = client.get(f"/api/items/{item['id']}")
    assert resp.status_code == 404


def test_list_items_filter_by_status(client):
    client.post("/api/items", json={"url": "https://www.instagram.com/reel/LIST1/"})
    resp = client.get("/api/items?status=NEW")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["pagination"]["total"] >= 1
    assert all(item["status"] == "NEW" for item in body["items"])


def test_watch_item(client):
    item = client.post("/api/items", json={"url": "https://www.instagram.com/reel/WATCH1/"}).get_json()["item"]
    resp = client.post(f"/api/items/{item['id']}/watch")
    assert resp.status_code == 200
    updated = resp.get_json()["item"]
    assert updated["watch_count"] == 1
    assert updated["watched_at"] is not None
    assert updated["status"] == "WATCHED"

    resp2 = client.post(f"/api/items/{item['id']}/watch")
    assert resp2.get_json()["item"]["watch_count"] == 2


def test_apply_item_creates_action(client):
    item = client.post("/api/items", json={"url": "https://www.instagram.com/reel/APPLY1/"}).get_json()["item"]
    resp = client.post(
        f"/api/items/{item['id']}/apply",
        json={"create_action": True, "action_title": "Do the thing", "implementation_notes": "notes here"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["item"]["status"] == "APPLIED"
    assert body["created_action_id"] is not None

    resp2 = client.get(f"/api/actions/{body['created_action_id']}")
    assert resp2.status_code == 200
    assert resp2.get_json()["action"]["title"] == "Do the thing"
