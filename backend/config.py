"""Central configuration. All values come from environment variables or a local .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Which AI provider to use: "gemini" (free tier, default) or "openai" ---
    llm_provider: str = "gemini"

    # --- Google Gemini (uses Google's OpenAI-compatible endpoint) ---
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"

    # --- OpenAI ---
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    request_timeout: float = 30.0  # seconds
    max_response_tokens: int = 500
    temperature: float = 0.5

    # --- Conversation memory ---
    max_history_messages: int = 12  # 6 user/assistant exchanges sent to the model
    max_history_chars: int = 6000  # hard cap on history size (keeps token use low)
    session_ttl_minutes: int = 60  # idle sessions are deleted after this
    max_sessions: int = 500

    # --- Document Q&A (LlamaIndex) ---
    documents_dir: Path = BASE_DIR / "documents"
    index_dir: Path = BASE_DIR / "storage"
    chunk_size: int = 512
    chunk_overlap: int = 64
    rag_top_k: int = 4
    rag_similarity_cutoff: float = 0.2

    # --- API protection / misc ---
    rate_limit_per_minute: int = 20
    log_level: str = "INFO"
    app_version: str = "1.0.0"

    @field_validator("openai_api_key", "gemini_api_key", mode="before")
    @classmethod
    def _clean_key(cls, value: object) -> str:
        # Remove accidental spaces or quotes around the key in .env
        return str(value or "").strip().strip("'\"")

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _clean_provider(cls, value: object) -> str:
        provider = str(value or "gemini").strip().lower()
        if provider not in {"gemini", "openai"}:
            raise ValueError("LLM_PROVIDER must be 'gemini' or 'openai'")
        return provider

    # ---- values for whichever provider is active ----
    @property
    def is_gemini(self) -> bool:
        return self.llm_provider == "gemini"

    @property
    def provider_label(self) -> str:
        return "Gemini" if self.is_gemini else "OpenAI"

    @property
    def key_env_name(self) -> str:
        return "GEMINI_API_KEY" if self.is_gemini else "OPENAI_API_KEY"

    @property
    def model_env_name(self) -> str:
        return "GEMINI_MODEL" if self.is_gemini else "OPENAI_MODEL"

    @property
    def api_key(self) -> str:
        return self.gemini_api_key if self.is_gemini else self.openai_api_key

    @property
    def api_base_url(self) -> str | None:
        """None means the OpenAI default endpoint."""
        return self.gemini_base_url if self.is_gemini else None

    @property
    def chat_model(self) -> str:
        return self.gemini_model if self.is_gemini else self.openai_model

    @property
    def embedding_model(self) -> str:
        return self.gemini_embedding_model if self.is_gemini else self.openai_embedding_model

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
