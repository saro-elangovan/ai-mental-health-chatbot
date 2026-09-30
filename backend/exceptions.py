"""Application errors and translation of OpenAI errors into friendly messages."""

import openai


class AppError(Exception):
    """An error that is safe to show to the user."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def map_openai_error(exc: Exception, key_name: str = "the API key", model_name: str = "the model setting") -> AppError:
    """Convert an OpenAI-SDK exception (also raised for Gemini) into a friendly AppError."""
    if isinstance(exc, openai.APITimeoutError):
        return AppError("AI_TIMEOUT", "The AI service took too long to respond. Please try again.", 504)
    if isinstance(exc, openai.APIConnectionError):
        return AppError("AI_UNREACHABLE", "Could not reach the AI service. Check your internet connection.", 502)
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return AppError("AI_AUTH_FAILED", f"The AI service rejected the API key. Check {key_name} on the server.", 503)
    if isinstance(exc, openai.RateLimitError):
        return AppError("AI_RATE_LIMITED", "The AI service is busy or the API quota is used up. Please try again later.", 429)
    if isinstance(exc, openai.NotFoundError):
        return AppError("AI_MODEL_NOT_FOUND", f"The configured AI model was not found. Check {model_name} on the server.", 503)
    if isinstance(exc, openai.BadRequestError):
        return AppError("AI_BAD_REQUEST", "The AI service could not process this request.", 400)
    return AppError("AI_FAILURE", "The AI service returned an error. Please try again.", 502)
