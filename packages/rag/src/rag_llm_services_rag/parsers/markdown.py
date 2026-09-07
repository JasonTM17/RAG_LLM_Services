"""Markdown document parser with heading hierarchy preservation."""

from __future__ import annotations

import re

from rag_llm_services_rag.parsers.base import DocumentParser, ParsedDocument, ParsedSection

_HEADING_REGEX = re.compile(r"^(#{1,6})\s+(.+)$")


class MarkdownParser(DocumentParser):
    """Parser for markdown documents that decomposes content along heading boundaries."""

    def supported_mime_types(self) -> set[str]:
        return {"text/markdown", "text/x-markdown"}

    def supported_extensions(self) -> set[str]:
        return {".md", ".markdown"}

    def parse(self, content: bytes, filename: str | None = None) -> ParsedDocument:
        """Decode markdown bytes and segment by header hierarchy."""
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

        lines = text.splitlines(keepends=True)
        sections: list[ParsedSection] = []

        current_header: str | None = None
        current_level: int = 0
        current_hierarchy: list[str] = []
        current_lines: list[str] = []

        def flush_section() -> None:
            nonlocal current_lines
            content_str = "".join(current_lines).strip()
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

        for line in lines:
            stripped = line.strip()
            match = _HEADING_REGEX.match(stripped)
            if match:
                flush_section()
                level = len(match.group(1))
                title = match.group(2).strip()

                # Adjust hierarchy stack based on heading depth
                if level > current_level:
                    current_hierarchy.append(title)
                elif level == current_level:
                    if current_hierarchy:
                        current_hierarchy[-1] = title
                    else:
                        current_hierarchy = [title]
                else:
                    # Ascended to a shallower heading
                    current_hierarchy = current_hierarchy[: level - 1] + [title]

                current_level = level
                current_header = title
                current_lines.append(line)
            else:
                current_lines.append(line)

        flush_section()

        # If document had no headings or empty sections
        if not sections and text.strip():
            sections.append(
                ParsedSection(
                    content=text.strip(),
                    page_number=None,
                    section_header=None,
                    hierarchy=[],
                    metadata={"filename": filename} if filename else {},
                )
            )

        return ParsedDocument(
            raw_text=text,
            sections=sections,
            metadata={"mime_type": "text/markdown", "filename": filename},
        )
