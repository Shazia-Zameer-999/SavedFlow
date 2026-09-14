def test_local_browser_sync_imports_ten_distinct_posts(client):
    entries = [{"url": f"https://www.instagram.com/reel/POST{i:02d}/"} for i in range(10)]
    response = client.post("/api/instagram/sync", json={
    "source": "local_playwright", "status": "COMPLETED", "items": entries
}, headers={"X-SavedFlow-Sync-Token": "test-sync-token"})
    body = response.get_json()
    assert body["imported"] == 10
    assert body["duplicates"] == 0
    assert client.get("/api/items?page_size=100").get_json()["pagination"]["total"] == 10


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


def test_local_browser_sync_stops_on_auth_challenge(client):
    response = client.post("/api/instagram/sync", json={
        "source": "local_playwright",
        "status": "LOGIN_CHALLENGE",
        "items": []
    }, headers={"X-SavedFlow-Sync-Token": "test-sync-token"})
    assert response.status_code == 401


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
