"""Chat orchestration: safety check -> memory -> AI model (Gemini or OpenAI) -> memory update."""

import openai
from openai import AsyncOpenAI

from .config import Settings
from .exceptions import AppError, map_openai_error
from .logger import get_logger
from .memory_service import MemoryService
from .models import ChatResponse
from .prompts import MEDICAL_BOUNDARY_NOTE, SYSTEM_PROMPT
from .safety_service import CRISIS_RESPONSE, check_message

log = get_logger("chat")

REDACTED_USER_TURN = "[Message withheld by safety layer]"


class ChatService:
    def __init__(self, settings: Settings, memory: MemoryService) -> None:
        self.settings = settings
        self.memory = memory
        self._client: AsyncOpenAI | None = None

    # ---- OpenAI ----------------------------------------------------
    def ensure_configured(self) -> None:
        if not self.settings.has_api_key:
            raise AppError(
                "MISSING_API_KEY",
                f"The server has no {self.settings.provider_label} API key. "
                f"Add {self.settings.key_env_name} to the .env file and restart.",
                503,
            )

    def _get_client(self) -> AsyncOpenAI:
        """Create the client once and reuse it (connection pooling)."""
        if self._client is None:
            # Gemini is reached through Google's OpenAI-compatible endpoint (base_url).
            self._client = AsyncOpenAI(
                api_key=self.settings.api_key,
                base_url=self.settings.api_base_url,
                timeout=self.settings.request_timeout,
                max_retries=1,
            )
        return self._client

    async def _call_llm(self, messages: list[dict[str, str]]) -> str:
        limit_arg = "max_tokens" if self.settings.is_gemini else "max_completion_tokens"
        try:
            response = await self._get_client().chat.completions.create(
                model=self.settings.chat_model,
                messages=messages,
                temperature=self.settings.temperature,
                **{limit_arg: self.settings.max_response_tokens},
            )
        except openai.OpenAIError as exc:
            log.warning("%s call failed: %s", self.settings.provider_label, type(exc).__name__)
            raise map_openai_error(exc, self.settings.key_env_name, self.settings.model_env_name) from exc
        text = (response.choices[0].message.content or "").strip()
        if not text:
            raise AppError("EMPTY_RESPONSE", "The AI returned an empty answer. Please try again.", 502)
        return text

    # ---- session helper -------------------------------------------
    def _resolve_session(self, session_id: str | None, lenient: bool = False) -> str:
        if session_id is None:
            return self.memory.create_session()
        try:
            self.memory.get_session(session_id)
            return session_id
        except AppError:
            if lenient:  # never show a person in crisis an error page
                return self.memory.create_session()
            raise

    # ---- main entry point -----------------------------------------
    async def reply(self, message: str, session_id: str | None) -> ChatResponse:
        safety = check_message(message)

        if safety.is_crisis:
            sid = self._resolve_session(session_id, lenient=True)
            # Do not keep the sensitive text; keep only a placeholder for context.
            self.memory.add_exchange(sid, REDACTED_USER_TURN, CRISIS_RESPONSE)
            log.info("chat session=%s crisis=True", sid[:8])
            return ChatResponse(reply=CRISIS_RESPONSE, session_id=sid, is_crisis=True)

        self.ensure_configured()
        sid = self._resolve_session(session_id)

        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += self.memory.get_context(sid)
        if safety.needs_medical_boundary:
            messages.append({"role": "system", "content": MEDICAL_BOUNDARY_NOTE})
        messages.append({"role": "user", "content": message})

        answer = await self._call_llm(messages)
        self.memory.add_exchange(sid, message, answer)
        log.info("chat session=%s chars_in=%d chars_out=%d", sid[:8], len(message), len(answer))
        return ChatResponse(reply=answer, session_id=sid, is_crisis=False)
