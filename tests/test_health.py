def test_health_ok(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["ai_configured"] is False  # conftest clears the key
    assert body["active_sessions"] == 0


def test_frontend_is_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Wellness Support" in res.text
    assert client.get("/script.js").status_code == 200
    assert client.get("/style.css").status_code == 200


def test_security_headers(client):
    res = client.get("/health")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in res.headers
