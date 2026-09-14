def test_create_action(client):
    item = client.post("/api/items", json={"url": "https://www.instagram.com/reel/ACT1/"}).get_json()["item"]
    resp = client.post("/api/actions", json={"item_id": item["id"], "title": "Try this trick"})
    assert resp.status_code == 201
    action = resp.get_json()["action"]
    assert action["status"] == "NOT_STARTED"
    assert action["item_id"] == item["id"]


def test_create_action_missing_fields(client):
    resp = client.post("/api/actions", json={"title": "no item id"})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "MISSING_FIELDS"


def test_create_action_invalid_item(client):
    from bson import ObjectId
    resp = client.post("/api/actions", json={"item_id": str(ObjectId()), "title": "orphan action"})
    assert resp.status_code == 404


def test_update_action_status_sets_completed_at(client):
    item = client.post("/api/items", json={"url": "https://www.instagram.com/reel/ACT2/"}).get_json()["item"]
    action = client.post("/api/actions", json={"item_id": item["id"], "title": "Do a thing"}).get_json()["action"]

    resp = client.patch(f"/api/actions/{action['id']}", json={"status": "COMPLETED", "result": "It worked!"})
    assert resp.status_code == 200
    updated = resp.get_json()["action"]
    assert updated["status"] == "COMPLETED"
    assert updated["completed_at"] is not None
    assert updated["result"] == "It worked!"


def test_update_action_invalid_status(client):
    item = client.post("/api/items", json={"url": "https://www.instagram.com/reel/ACT3/"}).get_json()["item"]
    action = client.post("/api/actions", json={"item_id": item["id"], "title": "Do a thing"}).get_json()["action"]
    resp = client.patch(f"/api/actions/{action['id']}", json={"status": "WHATEVER"})
    assert resp.status_code == 400


def test_list_actions_filter_by_status(client):
    item = client.post("/api/items", json={"url": "https://www.instagram.com/reel/ACT4/"}).get_json()["item"]
    client.post("/api/actions", json={"item_id": item["id"], "title": "First"})
    resp = client.get("/api/actions?status=NOT_STARTED")
    assert resp.status_code == 200
    assert all(a["status"] == "NOT_STARTED" for a in resp.get_json()["actions"])
