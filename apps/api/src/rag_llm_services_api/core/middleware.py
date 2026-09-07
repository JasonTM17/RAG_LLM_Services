"""Request ID middleware.

Honors a well-formed incoming ``X-Request-ID`` header, otherwise generates a
fresh one, publishes the resolved ID to the observability ContextVar for the
duration of the request, and always echoes it on the response header. The
ContextVar is reset in a ``finally`` block so no ID bleeds into a subsequent
request executed by the same task.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from rag_llm_services_observability.context import request_id_var, set_request_id
from rag_llm_services_shared.constants import CLIENT_REQUEST_ID_PATTERN, REQUEST_ID_HEADER

_CLIENT_REQUEST_ID_PATTERN = CLIENT_REQUEST_ID_PATTERN


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Resolve, publish, and echo a per-request correlation ID.

    An incoming ``X-Request-ID`` header is honored only when it fully matches
    ``^[A-Za-z0-9_-]{8,64}$``; malformed client-supplied values are replaced
    with a generated ``uuid4().hex`` rather than echoed.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Set the request ID, run the rest of the stack, echo it in the response."""
        incoming = request.headers.get(REQUEST_ID_HEADER)
        if incoming is not None and _CLIENT_REQUEST_ID_PATTERN.fullmatch(incoming):
            request_id = incoming
        else:
            request_id = uuid.uuid4().hex

        token = set_request_id(request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            request_id_var.reset(token)
