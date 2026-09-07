"""Prometheus metrics endpoint."""

from fastapi import APIRouter
from fastapi.responses import Response

from rag_llm_services_observability.metrics import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter(tags=["observability"])


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Return Prometheus text exposition without touching external providers."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
