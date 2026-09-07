"""Safe provider error mapping."""

from __future__ import annotations

import httpx

from rag_llm_services_shared.errors import AppError


class LLMProviderError(AppError):
    """Provider error safe to pass through the API error envelope."""

    default_code = "LLM_PROVIDER_ERROR"
    default_status = 502

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        provider_status: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message, code=code, status_code=status_code)
        self.provider_status = provider_status
        self.retryable = retryable


_STATUS_MAP: dict[int, tuple[str, str, int, bool]] = {
    400: ("LLM_INVALID_REQUEST", "LLM provider rejected the request", 502, False),
    401: ("LLM_AUTHENTICATION_FAILED", "LLM provider authentication failed", 503, False),
    402: ("LLM_INSUFFICIENT_BALANCE", "LLM provider balance is insufficient", 503, False),
    422: ("LLM_INVALID_PARAMETERS", "LLM provider rejected request parameters", 502, False),
    429: ("LLM_RATE_LIMITED", "LLM provider rate limit reached", 429, True),
    500: ("LLM_PROVIDER_INTERNAL_ERROR", "LLM provider returned an internal error", 502, True),
    503: ("LLM_PROVIDER_UNAVAILABLE", "LLM provider is unavailable", 503, True),
}


def map_provider_status(status_code: int) -> LLMProviderError:
    """Map provider HTTP status to a stable safe application error."""
    code, message, app_status, retryable = _STATUS_MAP.get(
        status_code,
        ("LLM_PROVIDER_ERROR", "LLM provider request failed", 502, status_code >= 500),
    )
    return LLMProviderError(
        message,
        code=code,
        status_code=app_status,
        provider_status=status_code,
        retryable=retryable,
    )


def map_httpx_error(exc: httpx.HTTPError) -> LLMProviderError:
    """Map network and timeout failures without exposing request details."""
    if isinstance(exc, httpx.TimeoutException):
        return LLMProviderError(
            "LLM provider request timed out",
            code="LLM_TIMEOUT",
            status_code=504,
            retryable=True,
        )
    return LLMProviderError(
        "LLM provider network request failed",
        code="LLM_NETWORK_ERROR",
        status_code=503,
        retryable=True,
    )
