def test_bulk_manual_import_counts(client):
    urls = [
        "https://www.instagram.com/reel/AAA111/",
        "https://www.instagram.com/reel/BBB222/",
        "https://www.instagram.com/p/CCC333/",
        "not-a-url",
        "https://example.com/reel/xyz/",
    ]
    resp = client.post("/api/import/manual", json={"urls": urls})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total_submitted"] == 5
    assert body["imported"] == 3
    assert body["invalid"] == 2
    assert body["duplicates"] == 0


def test_bulk_manual_import_detects_duplicates_within_batch_and_db(client):
    resp = client.post("/api/import/manual", json={
        "urls": ["https://www.instagram.com/reel/DUPA/", "https://www.instagram.com/reel/DUPA/"]
    })
    body = resp.get_json()
    assert body["imported"] == 1
    assert body["duplicates"] == 1

    resp2 = client.post("/api/import/manual", json={"urls": ["https://www.instagram.com/reel/DUPA/"]})
    body2 = resp2.get_json()
    assert body2["imported"] == 0
    assert body2["duplicates"] == 1


def test_manual_import_missing_urls_field(client):
    resp = client.post("/api/import/manual", json={})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "MISSING_FIELDS"


def test_instagram_api_import_reports_unavailable(client):
    resp = client.post("/api/import/instagram")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is False
    assert body["available"] is False
    assert "reason" in body


def test_export_import_unsupported_format(client):
    resp = client.post("/api/import/export", json={"totally": "unrelated", "structure": 123})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["format_supported"] is False


def test_export_import_recognized_format(client):
    export_data = {
        "saved_saved_media": {
            "media_list_data": [],
            "string_map_data": {}
        },
        "some_list": [
            {
                "title": "cool.dev",
                "string_map_data": {
                    "Href": {"href": None, "value": "https://www.instagram.com/reel/EXPORT1/"},
                    "Time": {"timestamp": 1700000000},
                }
            }
        ]
    }
    resp = client.post("/api/import/export", json=export_data)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["format_supported"] is True
    assert body["result"]["imported"] == 1


def test_export_import_never_crashes_on_malformed_data(client):
    resp = client.post("/api/import/export", json={"a": [1, 2, {"b": None}]})
    assert resp.status_code == 200
    assert resp.get_json()["format_supported"] is False


def test_import_status(client):
    client.post("/api/import/manual", json={"urls": ["https://www.instagram.com/reel/STAT1/"]})
    resp = client.get("/api/import/status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total_items"] >= 1
    assert body["instagram_api_saved_content_available"] is False
