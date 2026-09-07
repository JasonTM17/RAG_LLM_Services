"""DOCX document parser using python-docx."""

from __future__ import annotations

import io
import re

import docx
from docx.opc.exceptions import PackageNotFoundError

from rag_llm_services_rag.parsers.base import DocumentParser, ParsedDocument, ParsedSection
from rag_llm_services_shared.errors import ValidationError

_HEADING_STYLE_PATTERN = re.compile(r"^heading\s*(\d+)$", re.IGNORECASE)


class DocxParser(DocumentParser):
    """Parser for Microsoft Word (.docx) documents with heading hierarchy extraction."""

    def supported_mime_types(self) -> set[str]:
        return {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }

    def supported_extensions(self) -> set[str]:
        return {".docx"}

    def parse(self, content: bytes, filename: str | None = None) -> ParsedDocument:
        """Extract paragraphs and table text from raw DOCX bytes."""
        try:
            doc = docx.Document(io.BytesIO(content))
        except (PackageNotFoundError, Exception) as exc:
            raise ValidationError(f"Invalid or corrupted DOCX document: {exc}") from exc

        sections: list[ParsedSection] = []
        raw_parts: list[str] = []

        current_header: str | None = None
        current_level: int = 0
        current_hierarchy: list[str] = []
        current_lines: list[str] = []

        def flush_section() -> None:
            nonlocal current_lines
            content_str = "\n".join(current_lines).strip()
            if content_str:
                sections.append(
                    ParsedSection(
                        content=content_str,
                        page_number=None,
                        section_header=current_header,
                        hierarchy=list(current_hierarchy),
                        metadata={"filename": filename} if filename else {},
                    )
                )
            current_lines = []

        # Iterate through block elements in document
        for paragraph in doc.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue

            raw_parts.append(text)
            style_name = paragraph.style.name if paragraph.style else ""
            match = _HEADING_STYLE_PATTERN.match(style_name)

            if match or style_name.lower() == "title":
                flush_section()
                level = int(match.group(1)) if match else 1
                title = text

                if level > current_level:
                    current_hierarchy.append(title)
                elif level == current_level:
                    if current_hierarchy:
                        current_hierarchy[-1] = title
                    else:
                        current_hierarchy = [title]
                else:
                    current_hierarchy = current_hierarchy[: level - 1] + [title]

                current_level = level
                current_header = title
                current_lines.append(text)
            else:
                current_lines.append(text)

        # Extract table content as well
        for table in doc.tables:
            table_rows: list[str] = []
            for row in table.rows:
                row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if row_cells:
                    table_rows.append(" | ".join(row_cells))
            if table_rows:
                table_text = "\n".join(table_rows)
                raw_parts.append(table_text)
                current_lines.append(table_text)

        flush_section()

        full_raw_text = "\n\n".join(raw_parts)

        return ParsedDocument(
            raw_text=full_raw_text,
            sections=sections,
            metadata={
                "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "filename": filename,
            },
        )
