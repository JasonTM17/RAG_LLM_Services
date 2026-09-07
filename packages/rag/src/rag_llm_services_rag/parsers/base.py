"""Base parser interfaces and parsed document data structures."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ParsedSection:
    """A structural section of a parsed document (e.g. page, heading section)."""

    content: str
    page_number: int | None = None
    section_header: str | None = None
    hierarchy: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedDocument:
    """Structured representation of a parsed document."""

    raw_text: str
    sections: list[ParsedSection] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class DocumentParser(ABC):
    """Abstract interface for format-specific document parsers."""

    @abstractmethod
    def parse(self, content: bytes, filename: str | None = None) -> ParsedDocument:
        """Parse raw file bytes into a structured ParsedDocument."""
        ...

    @abstractmethod
    def supported_mime_types(self) -> set[str]:
        """Return the set of MIME types supported by this parser."""
        ...

    @abstractmethod
    def supported_extensions(self) -> set[str]:
        """Return the set of file extensions (e.g. .pdf) supported by this parser."""
        ...
