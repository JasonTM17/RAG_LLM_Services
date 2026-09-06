"""Request-scoped context variables used for log correlation.

Middleware sets the request ID once per request; filters, formatters, and
error handlers read it through :func:`get_request_id` without threading the
value through every call signature.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Return the current request ID, or ``None`` outside a request."""
    return request_id_var.get()


def set_request_id(value: str) -> Token[str | None]:
    """Set the current request ID and return a reset token."""
    return request_id_var.set(value)
