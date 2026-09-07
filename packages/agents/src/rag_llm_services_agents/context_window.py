"""Local context window management for agent prompts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class HistoryMessage:
    """One local conversation history message."""

    role: str
    content: str


@dataclass(frozen=True)
class ContextWindowSelection:
    """Bounded message selection for one agent run."""

    messages: tuple[HistoryMessage, ...]
    omitted_count: int
    total_chars: int


class ContextWindowManager:
    """Select recent local messages without relying on provider-side memory."""

    def __init__(self, *, max_messages: int = 8, max_chars: int = 12000) -> None:
        if max_messages < 1:
            raise ValueError("max_messages must be at least 1")
        if max_chars < 1:
            raise ValueError("max_chars must be at least 1")
        self.max_messages = max_messages
        self.max_chars = max_chars

    def select(self, history: Sequence[HistoryMessage | tuple[str, str]]) -> ContextWindowSelection:
        """Keep the newest messages while staying within count and character limits."""
        normalized = tuple(_normalize_message(message) for message in history)
        selected_reversed: list[HistoryMessage] = []
        total_chars = 0

        for message in reversed(normalized):
            if len(selected_reversed) >= self.max_messages:
                break
            message_chars = len(message.role) + len(message.content)
            if selected_reversed and total_chars + message_chars > self.max_chars:
                break
            if message_chars > self.max_chars:
                truncated = HistoryMessage(
                    role=message.role,
                    content=message.content[-self.max_chars :],
                )
                selected_reversed.append(truncated)
                total_chars = self.max_chars
                break
            selected_reversed.append(message)
            total_chars += message_chars

        selected = tuple(reversed(selected_reversed))
        omitted = max(0, len(normalized) - len(selected))
        return ContextWindowSelection(
            messages=selected,
            omitted_count=omitted,
            total_chars=total_chars,
        )


def _normalize_message(message: HistoryMessage | tuple[str, str]) -> HistoryMessage:
    if isinstance(message, HistoryMessage):
        return message
    role, content = message
    return HistoryMessage(role=role, content=content)
