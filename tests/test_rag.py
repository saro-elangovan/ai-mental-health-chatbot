"""Document Q&A tests using LlamaIndex mock models - no real OpenAI calls are made."""

import asyncio

import pytest
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.llms import MockLLM

from backend.config import Settings
from backend.exceptions import AppError
from backend.rag_service import RAGService


def make_service(tmp_path, with_docs=True):
    docs = tmp_path / "docs"
    docs.mkdir()
    if with_docs:
        (docs / "guide.txt").write_text("Slow breathing helps the body relax. Sleep at regular times.")
        (docs / "README.md").write_text("ignored file")
    settings = Settings(openai_api_key="", gemini_api_key="", documents_dir=docs, index_dir=tmp_path / "storage")
    return RAGService(settings, llm=MockLLM(), embed_model=MockEmbedding(embed_dim=8))


def test_no_documents_gives_clear_error(tmp_path):
    service = make_service(tmp_path, with_docs=False)
    with pytest.raises(AppError) as err:
        asyncio.run(service.query("How do I relax?"))
    assert err.value.code == "NO_DOCUMENTS"


def test_readme_is_ignored_and_status(tmp_path):
    service = make_service(tmp_path)
    status = service.status()
    assert status.documents == ["guide.txt"]
    assert status.count == 1 and status.indexed is False


def test_index_is_built_saved_and_reused(tmp_path):
    service = make_service(tmp_path)
    first = asyncio.run(service.get_index())
    assert (tmp_path / "storage" / "fingerprint.json").exists()
    assert asyncio.run(service.get_index()) is first  # cached in memory, not rebuilt

    # A brand-new service loads the saved index from disk instead of re-embedding
    other = RAGService(service.settings, llm=MockLLM(), embed_model=MockEmbedding(embed_dim=8))
    assert asyncio.run(other.get_index()) is not None


def test_query_returns_answer_with_sources(tmp_path):
    service = make_service(tmp_path)
    result = asyncio.run(service.query("How can I relax?"))
    assert result.found is True
    assert result.sources and result.sources[0].file == "guide.txt"


def test_crisis_question_short_circuits(tmp_path):
    service = make_service(tmp_path)
    result = asyncio.run(service.query("I want to kill myself"))
    assert result.is_crisis is True
    assert service.status().indexed is False  # no indexing / API work was done


def test_endpoint_without_key_and_without_docs(client):
    res = client.post("/document/query", json={"question": "How to sleep better?"})
    assert res.status_code in (404, 503)
    assert "error" in res.json()
