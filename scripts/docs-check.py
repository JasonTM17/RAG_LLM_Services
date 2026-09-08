"""Validate the documentation contract used by Phase 15."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DOCS = (
    "docs/architecture/system-overview.md",
    "docs/rag/ingestion-pipeline.md",
    "docs/rag/retrieval-pipeline.md",
    "docs/agent/agent-architecture.md",
    "docs/n8n/workflows.md",
    "docs/observability/metrics.md",
    "docs/deployment/docker.md",
    "docs/security/threat-model.md",
)

REQUIRED_ADRS = tuple(f"docs/adr/ADR-{idx:03d}" for idx in range(1, 7))

README_HEADINGS = (
    "## Overview",
    "## Architecture",
    "## Features",
    "## Technology Stack",
    "## Quick Start",
    "## Environment Configuration",
    "## Docker",
    "## API Usage",
    "## n8n",
    "## Prometheus and Grafana",
    "## Testing",
    "## Evaluation",
    "## Security",
    "## Repository Structure",
)

ADR_SECTIONS = (
    "## Status",
    "## Context",
    "## Decision",
    "## Alternatives Considered",
    "## Consequences",
    "## Larger-Scale Path",
)

SECRET_SHAPED_RE = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|gh[po]_[A-Za-z0-9]{30,}|Bearer\s+[A-Za-z0-9._\-]{20,})"
)
WINDOWS_ABSOLUTE_RE = re.compile(r"\b[A-Za-z]:[\\/]")
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
URI_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)


def _markdown_files() -> list[Path]:
    files = [REPO_ROOT / "README.md", REPO_ROOT / "CONTRIBUTING.md"]
    files.extend(sorted((REPO_ROOT / "docs").rglob("*.md")))
    return [path for path in files if path.exists()]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _validate_required_paths(errors: list[str]) -> None:
    for rel in REQUIRED_DOCS:
        if not (REPO_ROOT / rel).is_file():
            errors.append(f"missing required documentation file: {rel}")

    adr_files = sorted((REPO_ROOT / "docs" / "adr").glob("ADR-*.md"))
    for prefix in REQUIRED_ADRS:
        matches = [
            path for path in adr_files if path.relative_to(REPO_ROOT).as_posix().startswith(prefix)
        ]
        if not matches:
            errors.append(f"missing required ADR: {prefix}")
            continue
        text = _read(matches[0])
        for section in ADR_SECTIONS:
            if section not in text:
                errors.append(f"{matches[0].relative_to(REPO_ROOT).as_posix()} missing {section}")


def _validate_readme(errors: list[str]) -> None:
    readme = REPO_ROOT / "README.md"
    if not readme.is_file():
        errors.append("missing README.md")
        return
    text = _read(readme)
    for heading in README_HEADINGS:
        if heading not in text:
            errors.append(f"README.md missing heading {heading}")
    if "CI, deployment," in text and "not implemented yet" in text:
        errors.append("README.md still describes CI as not implemented")


def _validate_links(path: Path, text: str, errors: list[str]) -> None:
    for match in MARKDOWN_LINK_RE.finditer(text):
        target = match.group(1).strip()
        if not target or target.startswith("#") or URI_RE.match(target):
            continue
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1]
        target_path = target.split("#", 1)[0]
        if not target_path:
            continue
        resolved = (path.parent / target_path).resolve()
        try:
            resolved.relative_to(REPO_ROOT.resolve())
        except ValueError:
            errors.append(f"{path.relative_to(REPO_ROOT).as_posix()}: link escapes repo: {target}")
            continue
        if not resolved.exists():
            errors.append(f"{path.relative_to(REPO_ROOT).as_posix()}: broken link: {target}")


def _validate_content(errors: list[str]) -> None:
    for path in _markdown_files():
        text = _read(path)
        rel = path.relative_to(REPO_ROOT).as_posix()
        if WINDOWS_ABSOLUTE_RE.search(text):
            errors.append(f"{rel}: contains a machine-specific absolute path")
        if SECRET_SHAPED_RE.search(text):
            errors.append(f"{rel}: contains credential-shaped material")
        _validate_links(path, text, errors)


def main() -> int:
    errors: list[str] = []
    _validate_required_paths(errors)
    _validate_readme(errors)
    _validate_content(errors)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("DOCS_CHECK_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
