"""PDF document parser using pypdf."""

from __future__ import annotations

import io
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from rag_llm_services_rag.parsers.base import DocumentParser, ParsedDocument, ParsedSection
from rag_llm_services_shared.errors import ValidationError


class PDFParser(DocumentParser):
    """Parser for Adobe PDF documents with per-page text extraction."""

    def supported_mime_types(self) -> set[str]:
        return {"application/pdf"}

    def supported_extensions(self) -> set[str]:
        return {".pdf"}

    def parse(self, content: bytes, filename: str | None = None) -> ParsedDocument:
        """Extract text page-by-page from raw PDF bytes."""
        try:
            reader = PdfReader(io.BytesIO(content))
        except (PdfReadError, Exception) as exc:
            raise ValidationError(f"Invalid or corrupted PDF document: {exc}") from exc

        if reader.is_encrypted:
            try:
                decrypt_res = reader.decrypt("")
                if decrypt_res == 0:
                    raise ValidationError(
                        "Password-protected or encrypted PDF documents are not supported"
                    )
            except Exception as exc:
                if isinstance(exc, ValidationError):
                    raise
                raise ValidationError(
                    f"Password-protected or encrypted PDF documents are not supported: {exc}"
                ) from exc

        sections: list[ParsedSection] = []
        page_texts: list[str] = []

        total_pages = len(reader.pages)
        for page_idx, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception:  # noqa: BLE001
                page_text = ""

            page_texts.append(page_text)
            stripped_text = page_text.strip()
            if stripped_text:
                sections.append(
                    ParsedSection(
                        content=stripped_text,
                        page_number=page_idx,
                        section_header=None,
                        hierarchy=[],
                        metadata={
                            "page": page_idx,
                            "total_pages": total_pages,
                            "filename": filename,
                        },
                    )
                )

        full_raw_text = "\n\n".join(t for t in page_texts if t.strip())

        doc_metadata: dict[str, Any] = {
            "mime_type": "application/pdf",
            "filename": filename,
            "total_pages": total_pages,
        }

        # Try extracting standard document info/metadata safely
        if reader.metadata:
            for k in ("title", "author", "subject", "creator"):
                val = getattr(reader.metadata, k, None)
                if val and isinstance(val, str):
                    doc_metadata[k] = val.strip()

        return ParsedDocument(
            raw_text=full_raw_text,
            sections=sections,
            metadata=doc_metadata,
        )
