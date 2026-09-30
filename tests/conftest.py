import os

# Must run BEFORE the app is imported: makes tests independent of any real .env key.
os.environ["OPENAI_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["LLM_PROVIDER"] = "gemini"

import pytest
from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:  # "with" runs the startup/lifespan code
        yield c


@pytest.fixture()
def fake_key(monkeypatch):
    """Pretend an API key exists (the model call itself is mocked in each test)."""
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-not-real")
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test-not-real")
