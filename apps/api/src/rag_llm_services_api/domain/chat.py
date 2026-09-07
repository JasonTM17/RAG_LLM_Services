"""Chat domain constants."""

from __future__ import annotations

from enum import StrEnum


class ChatMessageRole(StrEnum):
    """Roles persisted in local chat history."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


DEFAULT_CHAT_HISTORY_LIMIT = 20
