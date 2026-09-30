"""FastAPI application: routes, error handlers, security headers, static frontend."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .chat_service import ChatService
from .config import get_settings
from .exceptions import AppError
from .logger import get_logger, setup_logging
from .memory_service import MemoryService
from .models import (
    ChatRequest,
    ChatResponse,
    DocumentQueryRequest,
    DocumentQueryResponse,
    DocumentStatus,
    HealthResponse,
    validate_session_id,
)
from .rag_service import RAGService
from .rate_limiter import RateLimiter, rate_limit

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
log = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    memory = MemoryService(
        max_messages=settings.max_history_messages,
        max_chars=settings.max_history_chars,
        ttl_seconds=settings.session_ttl_minutes * 60,
        max_sessions=settings.max_sessions,
    )
    app.state.settings = settings
    app.state.memory = memory
    app.state.chat_service = ChatService(settings, memory)
    app.state.rag_service = RAGService(settings)
    app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute)
    if not settings.has_api_key:
        log.warning("%s is not set. Chat and document Q&A will return an error until it is.", settings.key_env_name)
    log.info("Application started (version %s, provider %s, model %s)", settings.app_version, settings.llm_provider, settings.chat_model)
    yield


app = FastAPI(
    title="AI Mental Health Support & Wellness Chatbot",
    description="General wellbeing information chatbot. Not a medical or emergency service.",
    version=get_settings().app_version,
    lifespan=lifespan,
)


# ---------------------------------------------------------------- errors
def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return _error(exc.status_code, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    message = str(first.get("msg", "Invalid request.")).removeprefix("Value error, ")
    if first.get("type") == "missing":
        message = "Required field is missing."
    return _error(422, "INVALID_REQUEST", message)


@app.exception_handler(Exception)
async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled server error: %s", type(exc).__name__)
    return _error(500, "SERVER_ERROR", "Something went wrong on the server. Please try again.")


# ---------------------------------------------------------------- security headers
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi")):
        # Strict CSP for the chat UI (Swagger UI needs looser rules, so it is excluded)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        )
    return response


# ---------------------------------------------------------------- routes
@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        ai_configured=settings.has_api_key,
        active_sessions=request.app.state.memory.active_count,
    )


@app.post("/chat", response_model=ChatResponse, tags=["Chat"], dependencies=[Depends(rate_limit)])
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    return await request.app.state.chat_service.reply(payload.message, payload.session_id)


@app.delete("/session/{session_id}", tags=["Chat"])
async def clear_session(session_id: str, request: Request) -> dict[str, bool]:
    try:
        sid = validate_session_id(session_id)
    except ValueError as exc:
        raise AppError("INVALID_SESSION", str(exc), 400) from exc
    request.app.state.memory.clear_session(sid)
    return {"cleared": True}


@app.post(
    "/document/query",
    response_model=DocumentQueryResponse,
    tags=["Documents"],
    dependencies=[Depends(rate_limit)],
)
async def document_query(payload: DocumentQueryRequest, request: Request) -> DocumentQueryResponse:
    return await request.app.state.rag_service.query(payload.question)


@app.get("/document/status", response_model=DocumentStatus, tags=["Documents"])
async def document_status(request: Request) -> DocumentStatus:
    return request.app.state.rag_service.status()


@app.post(
    "/document/reindex",
    response_model=DocumentStatus,
    tags=["Documents"],
    dependencies=[Depends(rate_limit)],
)
async def document_reindex(request: Request) -> DocumentStatus:
    await request.app.state.rag_service.get_index(force=True)
    return request.app.state.rag_service.status()


# The frontend is served by FastAPI itself, so the browser and API share one origin
# (no CORS configuration needed). This must stay LAST so it does not shadow API routes.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
