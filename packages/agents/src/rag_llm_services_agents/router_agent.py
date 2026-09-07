"""Deterministic router intent classification for agent workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class AgentIntent(StrEnum):
    """Supported high-level user intents."""

    ASK = "ASK"
    EXPLAIN = "EXPLAIN"
    DEEP_DIVE = "DEEP_DIVE"
    SUMMARIZE = "SUMMARIZE"
    QUIZ = "QUIZ"
    FLASHCARD = "FLASHCARD"
    LEARNING_PLAN = "LEARNING_PLAN"
    COMPARE = "COMPARE"
    EXAM = "EXAM"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class IntentRoute:
    """Router decision with a deterministic confidence score."""

    intent: AgentIntent
    confidence: float
    reason: str


class RouterAgent:
    """Map free-form user requests to bounded agent workflows."""

    _KEYWORDS: tuple[tuple[AgentIntent, tuple[str, ...], str], ...] = (
        (
            AgentIntent.LEARNING_PLAN,
            ("learning plan", "study plan", "roadmap", "schedule"),
            "learning plan keyword",
        ),
        (
            AgentIntent.FLASHCARD,
            ("flashcard", "flashcards", "flash card", "flash cards", "anki"),
            "flashcard keyword",
        ),
        (AgentIntent.QUIZ, ("quiz", "practice questions", "question set"), "quiz keyword"),
        (AgentIntent.EXAM, ("exam", "mock test", "test me"), "exam keyword"),
        (
            AgentIntent.COMPARE,
            ("compare", "versus", "vs.", "difference between"),
            "compare keyword",
        ),
        (AgentIntent.SUMMARIZE, ("summarize", "summary", "recap"), "summary keyword"),
        (AgentIntent.DEEP_DIVE, ("deep dive", "in depth", "thoroughly"), "deep dive keyword"),
        (AgentIntent.EXPLAIN, ("explain", "why does", "how does"), "explain keyword"),
        (AgentIntent.REVIEW, ("review", "revise", "check my understanding"), "review keyword"),
    )

    def route(self, message: str) -> IntentRoute:
        """Return the best route without exposing private context to the model."""
        normalized = " ".join(message.strip().lower().split())
        if not normalized:
            return IntentRoute(AgentIntent.ASK, 0.25, "empty request fallback")

        for intent, keywords, reason in self._KEYWORDS:
            if any(_contains_keyword(normalized, keyword) for keyword in keywords):
                return IntentRoute(intent=intent, confidence=0.9, reason=reason)

        if normalized.endswith("?") or normalized.split(" ", 1)[0] in {"what", "who", "when"}:
            return IntentRoute(AgentIntent.ASK, 0.75, "question fallback")
        return IntentRoute(AgentIntent.ASK, 0.5, "default ask fallback")


def _contains_keyword(message: str, keyword: str) -> bool:
    if " " in keyword or "." in keyword:
        return keyword in message
    return re.search(rf"\b{re.escape(keyword)}\b", message) is not None
