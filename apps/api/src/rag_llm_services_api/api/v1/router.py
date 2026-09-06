"""Versioned API surface under /api/v1.

Contract: routers in this package delegate to application services and
declare typed request/response models. They must not execute SQL directly,
construct prompts, or instantiate provider clients. Phase 02 ships the empty
router scaffold; domain routes arrive with their phases (documents Phase 03,
chat Phase 06/07, study Phase 07).
"""

from fastapi import APIRouter

router = APIRouter()
