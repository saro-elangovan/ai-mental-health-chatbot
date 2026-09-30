import pytest

from backend.safety_service import CRISIS_RESPONSE, check_message


@pytest.mark.parametrize(
    "text",
    [
        "I want to kill myself",
        "i don't want to live anymore",
        "I DON’T WANT TO LIVE ANYMORE",  # curly apostrophe + capitals
        "thinking about suicide",
        "I've been self-harming",
        "everyone would be better off without me",
        "I feel like there's no reason to live",
        "I want to hurt myself",
        "I'm going to hurt them",
    ],
)
def test_crisis_detected(text):
    assert check_message(text).is_crisis


@pytest.mark.parametrize(
    "text",
    [
        "How can I sleep better?",
        "I feel stressed about exams",
        "This homework is killing me",
        "What is a breathing exercise for anxiety?",
        "I'm feeling sad today",
    ],
)
def test_normal_messages_not_flagged(text):
    assert not check_message(text).is_crisis


@pytest.mark.parametrize(
    "text", ["Do I have depression?", "Should I stop taking my medication?", "What dose of sertraline is normal?"]
)
def test_medical_boundary_flag(text):
    assert check_message(text).needs_medical_boundary


def test_crisis_response_content():
    assert "not an emergency service" in CRISIS_RESPONSE
    assert "emergency number" in CRISIS_RESPONSE


def test_crisis_chat_needs_no_api_key(client):
    """The safety layer answers WITHOUT calling OpenAI (works even with no key)."""
    res = client.post("/chat", json={"message": "I want to kill myself"})
    assert res.status_code == 200
    body = res.json()
    assert body["is_crisis"] is True
    assert "not an emergency service" in body["reply"]
    assert body["session_id"]


def test_crisis_with_expired_session_still_gets_help(client):
    res = client.post(
        "/chat",
        json={"message": "I want to die", "session_id": "3f2b8c1e-8f4d-4f0a-9c55-0d5b8e1f2a11"},
    )
    assert res.status_code == 200
    assert res.json()["is_crisis"] is True
