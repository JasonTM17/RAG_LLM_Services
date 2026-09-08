"""Central security policy helpers for API assembly and settings validation."""

from __future__ import annotations

from urllib.parse import urlparse

LOCAL_ORIGIN_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

SECURITY_RESPONSE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
}


def validate_cors_origins_for_environment(origins: list[str], env: str) -> list[str]:
    """Validate CORS origins with stricter production rules."""
    if "*" in origins:
        raise ValueError("CORS_ORIGINS must not contain '*' (credentials are enabled)")

    normalized: list[str] = []
    for origin in origins:
        parsed = urlparse(origin.strip())
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("CORS_ORIGINS entries must be absolute origins")
        if parsed.username or parsed.password:
            raise ValueError("CORS_ORIGINS entries must not include credentials")
        if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
            raise ValueError("CORS_ORIGINS entries must not include path, query, or fragment")
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("CORS_ORIGINS entries must use http or https")

        host = (parsed.hostname or "").lower()
        if env == "production":
            if parsed.scheme != "https":
                raise ValueError("Production CORS origins must use https")
            if host in LOCAL_ORIGIN_HOSTS or host.endswith(".local"):
                raise ValueError("Production CORS origins must not target local hosts")

        normalized.append(f"{parsed.scheme}://{parsed.netloc}")

    if env == "production" and not normalized:
        raise ValueError("Production CORS_ORIGINS must include at least one allowed origin")
    return normalized


__all__ = [
    "LOCAL_ORIGIN_HOSTS",
    "SECURITY_RESPONSE_HEADERS",
    "validate_cors_origins_for_environment",
]
