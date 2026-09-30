import pytest

from backend.chat_service import ChatService


def test_empty_message_rejected(client):
    res = client.post("/chat", json={"message": "   "})
    assert res.status_code == 422
    assert res.json()["error"]["message"] == "Message cannot be empty."


def test_too_long_message_rejected(client):
    res = client.post("/chat", json={"message": "a" * 2001})
    assert res.status_code == 422
    assert "too long" in res.json()["error"]["message"]


def test_missing_field_rejected(client):
    res = client.post("/chat", json={})
    assert res.status_code == 422


def test_invalid_session_format(client):
    res = client.post("/chat", json={"message": "hi", "session_id": "not-a-uuid"})
    assert res.status_code == 422
    assert "Invalid session" in res.json()["error"]["message"]


def test_missing_api_key_gives_friendly_error(client):
    res = client.post("/chat", json={"message": "How can I relax?"})
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "MISSING_API_KEY"


def test_unknown_session_returns_404(client, fake_key):
    res = client.post(
        "/chat",
        json={"message": "hello", "session_id": "3f2b8c1e-8f4d-4f0a-9c55-0d5b8e1f2a11"},
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_session_memory_and_clear(client, fake_key, monkeypatch):
    seen_messages = []

    async def fake_llm(self, messages):
        seen_messages.append(messages)
        return f"reply {len(seen_messages)}"

    monkeypatch.setattr(ChatService, "_call_llm", fake_llm)

    first = client.post("/chat", json={"message": "I feel stressed about exams"}).json()
    sid = first["session_id"]
    assert first["reply"] == "reply 1"

    second = client.post("/chat", json={"message": "What can I do tonight?", "session_id": sid}).json()
    assert second["session_id"] == sid

    # The second model call must include the first exchange (session memory works)
    contents = [m["content"] for m in seen_messages[1]]
    assert "I feel stressed about exams" in contents
    assert "reply 1" in contents
    assert seen_messages[1][0]["role"] == "system"

    # Clearing removes the session
    assert client.delete(f"/session/{sid}").json() == {"cleared": True}
    assert client.delete(f"/session/{sid}").status_code == 404


def test_history_is_limited(client, fake_key, monkeypatch):
    async def fake_llm(self, messages):
        return "ok"

    monkeypatch.setattr(ChatService, "_call_llm", fake_llm)
    sid = client.post("/chat", json={"message": "m0"}).json()["session_id"]
    for i in range(1, 20):
        client.post("/chat", json={"message": f"m{i}", "session_id": sid})
    memory = client.app.state.memory
    assert len(memory.get_context(sid)) <= 12


def test_medical_question_adds_boundary_note(client, fake_key, monkeypatch):
    captured = {}

    async def fake_llm(self, messages):
        captured["messages"] = messages
        return "Please ask your doctor."

    monkeypatch.setattr(ChatService, "_call_llm", fake_llm)
    client.post("/chat", json={"message": "Should I stop taking my medication?"})
    assert any("Do NOT diagnose" in m["content"] for m in captured["messages"] if m["role"] == "system")


def test_delete_invalid_session_id(client):
    assert client.delete("/session/abc").status_code == 400


def test_rate_limit(client, fake_key, monkeypatch):
    async def fake_llm(self, messages):
        return "ok"

    monkeypatch.setattr(ChatService, "_call_llm", fake_llm)
    client.app.state.rate_limiter.limit = 3
    codes = [client.post("/chat", json={"message": "hi"}).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429
