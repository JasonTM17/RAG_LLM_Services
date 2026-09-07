"""FastAPI exception handlers that render the shared error envelope.

Every failure mode maps to ``{"error": {"code", "message", "request_id"}}``.
Client-visible messages are static or developer-controlled: pydantic error
details, the content of arbitrary exceptions, and tracebacks never reach the
response body; they are logged server-side only.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from rag_llm_services_api.core.errors import AppError
from rag_llm_services_observability.context import get_request_id, request_id_var, set_request_id
from rag_llm_services_shared.constants import REQUEST_ID_HEADER
from rag_llm_services_shared.envelope import ErrorBody, ErrorEnvelope

logger = logging.getLogger(__name__)

_STATUS_CODE_TO_CODE = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
_ExceptionHandler = Callable[[Request, Exception], Response | Awaitable[Response]]


def _error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    request: Request | None = None,
) -> JSONResponse:
    """Serialize the shared envelope with the current request ID attached."""
    req_id = getattr(request.state, "request_id", None) if request is not None else None
    if req_id is None:
        req_id = get_request_id()
    envelope = ErrorEnvelope(error=ErrorBody(code=code, message=message, request_id=req_id))
    headers = {REQUEST_ID_HEADER: req_id} if req_id else None
    return JSONResponse(status_code=status_code, content=envelope.model_dump(), headers=headers)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Map application errors onto their declared status and machine code."""
    log = logger.warning if exc.status_code < 500 else logger.error
    log(
        "Application error",
        extra={"code": exc.code, "status": exc.status_code, "path": request.url.path},
    )
    return _error_response(exc.status_code, exc.code, exc.message, request=request)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Reject malformed requests with a static message; log the count only.

    Pydantic error details (locations, messages, input values) are never
    echoed to the client.
    """
    logger.warning(
        "Request validation failed",
        extra={"path": request.url.path, "errors_count": len(exc.errors())},
    )
    return _error_response(422, "VALIDATION_ERROR", "Request validation failed", request=request)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Map Starlette HTTP exceptions onto stable machine codes."""
    code = _STATUS_CODE_TO_CODE.get(exc.status_code, f"HTTP_{exc.status_code}")
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    logger.warning(
        "HTTP exception",
        extra={"status": exc.status_code, "path": request.url.path},
    )
    return _error_response(exc.status_code, code, message, request=request)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a generic 500; the traceback stays in server logs only."""
    req_id = getattr(request.state, "request_id", None) or get_request_id()
    token = None
    if req_id and get_request_id() is None:
        token = set_request_id(req_id)
    try:
        logger.exception("Unhandled exception", extra={"path": request.url.path})
    finally:
        if token is not None:
            request_id_var.reset(token)
    return _error_response(500, "INTERNAL_ERROR", "Internal server error", request=request)


def register_exception_handlers(app: FastAPI) -> None:
    """Install the envelope-rendering handlers on ``app``."""
    app.add_exception_handler(AppError, cast(_ExceptionHandler, app_error_handler))
    app.add_exception_handler(
        RequestValidationError,
        cast(_ExceptionHandler, validation_error_handler),
    )
    app.add_exception_handler(
        StarletteHTTPException, cast(_ExceptionHandler, http_exception_handler)
    )
    app.add_exception_handler(Exception, unhandled_exception_handler)
