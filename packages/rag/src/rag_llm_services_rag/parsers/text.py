"""Plain text parser."""

from __future__ import annotations

from rag_llm_services_rag.parsers.base import DocumentParser, ParsedDocument, ParsedSection


class TextParser(DocumentParser):
    """Parser for plain text documents."""

    def supported_mime_types(self) -> set[str]:
        return {"text/plain"}

    def supported_extensions(self) -> set[str]:
        return {".txt"}

    def parse(self, content: bytes, filename: str | None = None) -> ParsedDocument:
        """Decode raw bytes into a ParsedDocument."""
        text: str
        if content.startswith((b"\xff\xfe", b"\xfe\xff")):
            try:
                text = content.decode("utf-16")
            except UnicodeDecodeError:
                text = content.decode("utf-8", errors="replace")
        else:
            for enc in ("utf-8", "latin-1"):
                try:
                    text = content.decode(enc)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            else:
                text = content.decode("utf-8", errors="replace")

        section = ParsedSection(
            content=text,
            page_number=1,
            section_header=None,
            hierarchy=[],
            metadata={"filename": filename} if filename else {},
        )
        return ParsedDocument(
            raw_text=text,
            sections=[section],
            metadata={"mime_type": "text/plain", "filename": filename},
        )
