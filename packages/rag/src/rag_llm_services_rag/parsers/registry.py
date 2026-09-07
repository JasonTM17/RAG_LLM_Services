"""Parser registry with MIME detection, extension fallback, and content sniffing."""

from __future__ import annotations

from pathlib import Path

from rag_llm_services_rag.parsers.base import DocumentParser
from rag_llm_services_rag.parsers.docx import DocxParser
from rag_llm_services_rag.parsers.markdown import MarkdownParser
from rag_llm_services_rag.parsers.pdf import PDFParser
from rag_llm_services_rag.parsers.text import TextParser
from rag_llm_services_shared.errors import UnsupportedMediaTypeError

# Map known alias or generic MIME types to canonical extensions/parsers
_MIME_ALIASES: dict[str, str] = {
    "text/x-markdown": "text/markdown",
    "application/x-pdf": "application/pdf",
    "text/x-python": "text/plain",
}


class ParserRegistry:
    """Registry managing format-specific document parsers."""

    def __init__(self) -> None:
        self._parsers_by_mime: dict[str, DocumentParser] = {}
        self._parsers_by_ext: dict[str, DocumentParser] = {}

    def register(self, parser: DocumentParser) -> None:
        """Register a document parser for its supported MIME types and extensions."""
        for mime in parser.supported_mime_types():
            self._parsers_by_mime[mime.lower()] = parser
        for ext in parser.supported_extensions():
            self._parsers_by_ext[ext.lower()] = parser

    def get_by_mime(self, mime_type: str) -> DocumentParser | None:
        """Look up parser strictly by MIME type."""
        normalized = mime_type.lower().split(";")[0].strip()
        canonical = _MIME_ALIASES.get(normalized, normalized)
        return self._parsers_by_mime.get(canonical)

    def get_by_extension(self, extension_or_filename: str) -> DocumentParser | None:
        """Look up parser by filename or extension."""
        suffix = Path(extension_or_filename).suffix.lower()
        return self._parsers_by_ext.get(suffix)

    def select_by_mime_and_sniff(
        self,
        mime_type: str,
        filename: str | None = None,
        content: bytes | None = None,
    ) -> DocumentParser:
        """Select the appropriate parser using MIME type, filename extension, or content sniffing.

        Raises UnsupportedMediaTypeError if no suitable parser is found.
        """
        # 1. Try explicit MIME type
        parser = self.get_by_mime(mime_type)
        if parser is not None:
            return parser

        # 2. Try filename extension if provided
        if filename:
            parser = self.get_by_extension(filename)
            if parser is not None:
                return parser

        # 3. Try content sniffing if bytes provided
        if content:
            sniffed_mime = self._sniff_content(content)
            if sniffed_mime:
                parser = self.get_by_mime(sniffed_mime)
                if parser is not None:
                    return parser

        target_desc = filename or mime_type
        raise UnsupportedMediaTypeError(
            f"No document parser available for MIME '{mime_type}' (target: '{target_desc}')"
        )

    def _sniff_content(self, content: bytes) -> str | None:
        """Sniff content type using magic bytes or puremagic if available."""
        if content.startswith(b"%PDF-"):
            return "application/pdf"
        if content.startswith(b"PK\x03\x04"):
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        try:
            import puremagic

            matches = puremagic.magic_string(content[:4096])
            if matches:
                return matches[0].mime_type
        except Exception:  # noqa: BLE001, S110
            pass
        return None


def get_default_parser_registry() -> ParserRegistry:
    """Build and return a ParserRegistry preloaded with standard parsers."""
    registry = ParserRegistry()
    registry.register(PDFParser())
    registry.register(TextParser())
    registry.register(MarkdownParser())
    registry.register(DocxParser())
    return registry
