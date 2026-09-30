"""Document Q&A with LlamaIndex (Retrieval-Augmented Generation).

Pipeline:
  documents/*.pdf|txt|md -> chunks -> embeddings -> vector index (saved to storage/)
  question -> retrieve top-k chunks -> drop weak matches -> LLM answers from chunks only

Efficiency:
- The index is built ONCE and saved to disk. It is rebuilt only if the files in the
  documents folder change (detected with a cheap fingerprint of name/size/mtime).
- Chunks below a similarity cutoff are discarded before calling the LLM. If nothing
  relevant is left, no LLM call is made at all and the user is told honestly.
"""

import asyncio
import hashlib
import json
import re
from pathlib import Path

import openai
from llama_index.core import (
    PromptTemplate,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai_like import OpenAILike

from .config import Settings
from .exceptions import AppError, map_openai_error
from .logger import get_logger
from .models import DocumentQueryResponse, DocumentStatus, SourceInfo
from .prompts import NOT_IN_DOCUMENTS_MESSAGE, RAG_QA_TEMPLATE
from .safety_service import CRISIS_RESPONSE, check_message

log = get_logger("rag")

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}
IGNORED_FILES = {"readme.md"}
FINGERPRINT_FILE = "fingerprint.json"


class RAGService:
    def __init__(self, settings: Settings, llm=None, embed_model=None) -> None:
        """`llm` and `embed_model` can be injected (used by tests to avoid real API calls)."""
        self.settings = settings
        self._llm = llm
        self._embed_model = embed_model
        self._index: VectorStoreIndex | None = None
        self._index_fingerprint: str | None = None
        self._lock = asyncio.Lock()

    # ---- helpers ---------------------------------------------------
    def _list_files(self) -> list[Path]:
        folder = self.settings.documents_dir
        if not folder.exists():
            return []
        return sorted(
            p for p in folder.rglob("*")
            if p.is_file()
            and p.suffix.lower() in SUPPORTED_EXTENSIONS
            and p.name.lower() not in IGNORED_FILES
        )

    def _fingerprint(self, files: list[Path]) -> str:
        parts = [self.settings.llm_provider, self.settings.embedding_model, str(self.settings.chunk_size)]
        for f in files:
            stat = f.stat()
            parts.append(f"{f.name}|{stat.st_size}|{stat.st_mtime_ns}")
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()

    def _require_models(self):
        if self._llm is not None and self._embed_model is not None:
            return self._llm, self._embed_model
        if not self.settings.has_api_key:
            raise AppError(
                "MISSING_API_KEY",
                f"The server has no {self.settings.provider_label} API key. "
                f"Add {self.settings.key_env_name} to the .env file and restart.",
                503,
            )
        # Both providers speak the OpenAI protocol, so the same LlamaIndex classes work.
        # For Gemini we simply point them at Google's OpenAI-compatible endpoint.
        self._embed_model = self._embed_model or OpenAIEmbedding(
            model_name=self.settings.embedding_model,
            api_key=self.settings.api_key,
            api_base=self.settings.api_base_url,
            embed_batch_size=16,
            timeout=self.settings.request_timeout,
            max_retries=1,
        )
        self._llm = self._llm or OpenAILike(
            model=self.settings.chat_model,
            api_key=self.settings.api_key,
            api_base=self.settings.api_base_url or "https://api.openai.com/v1",
            is_chat_model=True,
            temperature=0.1,
            max_tokens=self.settings.max_response_tokens,
            timeout=self.settings.request_timeout,
            max_retries=1,
        )
        return self._llm, self._embed_model

    # ---- index building (blocking work, run in a thread) -----------
    def _build_or_load(self, force: bool) -> tuple[VectorStoreIndex, str]:
        files = self._list_files()
        if not files:
            raise AppError(
                "NO_DOCUMENTS",
                "No documents found. Add .pdf, .txt or .md files to the documents folder.",
                404,
            )
        _, embed_model = self._require_models()
        fingerprint = self._fingerprint(files)
        index_dir = self.settings.index_dir
        fp_file = index_dir / FINGERPRINT_FILE

        if not force and fp_file.exists():
            try:
                saved = json.loads(fp_file.read_text(encoding="utf-8")).get("fingerprint")
                if saved == fingerprint:
                    storage = StorageContext.from_defaults(persist_dir=str(index_dir))
                    index = load_index_from_storage(storage, embed_model=embed_model)
                    log.info("Loaded saved index from disk (%d document files)", len(files))
                    return index, fingerprint
            except Exception as exc:  # corrupted index -> just rebuild
                log.warning("Saved index could not be loaded (%s); rebuilding", type(exc).__name__)

        try:
            documents = SimpleDirectoryReader(input_files=[str(f) for f in files]).load_data()
        except Exception as exc:
            log.error("Document loading failed: %s", type(exc).__name__)
            raise AppError(
                "DOCUMENT_LOAD_FAILED",
                "Could not read the documents. Make sure the files are valid, unencrypted PDF/TXT/MD files.",
                500,
            ) from exc
        if not any(d.text.strip() for d in documents):
            raise AppError(
                "DOCUMENTS_EMPTY",
                "The documents contain no readable text (scanned PDFs need OCR first).",
                422,
            )

        splitter = SentenceSplitter(
            chunk_size=self.settings.chunk_size, chunk_overlap=self.settings.chunk_overlap
        )
        index = VectorStoreIndex.from_documents(
            documents, embed_model=embed_model, transformations=[splitter]
        )
        index_dir.mkdir(parents=True, exist_ok=True)
        index.storage_context.persist(persist_dir=str(index_dir))
        fp_file.write_text(json.dumps({"fingerprint": fingerprint}), encoding="utf-8")
        log.info("Built new index from %d files / %d pages", len(files), len(documents))
        return index, fingerprint

    async def get_index(self, force: bool = False) -> VectorStoreIndex:
        async with self._lock:
            files = self._list_files()
            current = self._fingerprint(files) if files else None
            if self._index is not None and not force and current == self._index_fingerprint:
                return self._index
            try:
                self._index, self._index_fingerprint = await asyncio.to_thread(self._build_or_load, force)
            except AppError:
                raise
            except openai.OpenAIError as exc:
                raise map_openai_error(exc, self.settings.key_env_name, self.settings.model_env_name) from exc
            except Exception as exc:
                log.error("Indexing failed: %s", type(exc).__name__)
                raise AppError("RAG_FAILURE", "Document indexing failed. Please try again.", 500) from exc
            return self._index

    def status(self) -> DocumentStatus:
        files = self._list_files()
        return DocumentStatus(
            count=len(files),
            documents=[f.name for f in files],
            indexed=self._index is not None,
        )

    # ---- querying --------------------------------------------------
    async def query(self, question: str) -> DocumentQueryResponse:
        if check_message(question).is_crisis:
            return DocumentQueryResponse(answer=CRISIS_RESPONSE, found=False, is_crisis=True)

        index = await self.get_index()
        llm, _ = self._require_models()
        engine = index.as_query_engine(
            llm=llm,
            similarity_top_k=self.settings.rag_top_k,
            node_postprocessors=[SimilarityPostprocessor(similarity_cutoff=self.settings.rag_similarity_cutoff)],
            text_qa_template=PromptTemplate(RAG_QA_TEMPLATE),
            response_mode="compact",
        )
        try:
            response = await asyncio.wait_for(
                engine.aquery(question), timeout=self.settings.request_timeout * 2
            )
        except asyncio.TimeoutError as exc:
            raise AppError("AI_TIMEOUT", "The AI service took too long to respond. Please try again.", 504) from exc
        except openai.OpenAIError as exc:
            raise map_openai_error(exc, self.settings.key_env_name, self.settings.model_env_name) from exc
        except AppError:
            raise
        except Exception as exc:
            log.error("Document query failed: %s", type(exc).__name__)
            raise AppError("RAG_FAILURE", "Document Q&A failed. Please try again.", 500) from exc

        answer = str(response).strip()
        if not response.source_nodes or answer.startswith("NOT_IN_DOCUMENTS") or not answer:
            return DocumentQueryResponse(answer=NOT_IN_DOCUMENTS_MESSAGE, found=False)

        log.info("document query: sources=%d chars_out=%d", len(response.source_nodes), len(answer))
        return DocumentQueryResponse(answer=answer, found=True, sources=self._sources(response))

    @staticmethod
    def _sources(response) -> list[SourceInfo]:
        seen: set[tuple[str, str | None]] = set()
        sources: list[SourceInfo] = []
        for item in response.source_nodes:
            meta = item.node.metadata or {}
            name = meta.get("file_name", "unknown")
            page = meta.get("page_label")
            if (name, page) in seen:
                continue
            seen.add((name, page))
            snippet = re.sub(r"\s+", " ", item.node.get_content()).strip()
            sources.append(
                SourceInfo(
                    file=name,
                    page=str(page) if page else None,
                    score=round(float(item.score), 2) if item.score is not None else None,
                    snippet=snippet[:200] + ("..." if len(snippet) > 200 else ""),
                )
            )
        return sources
