"""Scan source for credential-shaped values and unsafe logging extras."""

from __future__ import annotations

import ast
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pnpm-store",
    ".pytest_cache",
    ".ruff_cache",
    ".turbo",
    ".venv",
    "htmlcov",
    "node_modules",
    "playwright-report",
    "test-results",
    "venv",
}

SKIP_FILES = {".env"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip"}

SENSITIVE_LOG_KEY_PATTERN = re.compile(
    r"api[-_]?key|authorization|password|secret|token|credential|cookie"
    r"|document[-_]?text|document[-_]?content|raw[-_]?text|raw[-_]?query|prompt|query",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SecretPattern:
    name: str
    pattern: re.Pattern[str]


SECRET_PATTERNS = (
    SecretPattern(
        "generic-api-key",
        re.compile(r"""(?i)(api[_-]?key|apikey)\s*[:=]\s*['"][A-Za-z0-9\-_]{20,}['"]"""),
    ),
    SecretPattern("aws-access-key-id", re.compile(r"AKIA[0-9A-Z]{16}")),
    SecretPattern(
        "aws-secret-access-key",
        re.compile(r"""(?i)aws[_-]?secret[_-]?access[_-]?key\s*[:=]\s*['"][A-Za-z0-9/+]{40}['"]"""),
    ),
    SecretPattern("jwt", re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")),
    SecretPattern(
        "quoted-password",
        re.compile(r"""(?i)(password|passwd|pwd)\s*[:=]\s*['"][^'"]{8,}['"]"""),
    ),
    SecretPattern(
        "private-key",
        re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    ),
    SecretPattern("github-token", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    SecretPattern("stripe-secret-key", re.compile(r"sk_(live|test)_[A-Za-z0-9]{24,}")),
    SecretPattern("bearer-token", re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]{20,}")),
)


def _git_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line.strip()]


def _is_scannable(path: Path) -> bool:
    rel_parts = path.relative_to(REPO_ROOT).parts
    if any(part in SKIP_DIRS for part in rel_parts):
        return False
    if path.name in SKIP_FILES or path.name.startswith(".env."):
        return False
    return path.suffix.lower() not in SKIP_SUFFIXES


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _scan_secret_patterns(paths: list[Path]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        text = _read(path)
        if text is None:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        for pattern in SECRET_PATTERNS:
            for match in pattern.pattern.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                findings.append(f"{rel}:{line_no}: secret-pattern:{pattern.name}")
    return findings


def _is_logging_call(node: ast.Call) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    return func.attr in {"debug", "info", "warning", "error", "exception", "critical"}


def _string_key(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _scan_logging_extras(paths: list[Path]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        rel_parts = path.relative_to(REPO_ROOT).parts
        if path.suffix != ".py" or rel_parts[0] not in {"apps", "packages"}:
            continue
        text = _read(path)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            rel = path.relative_to(REPO_ROOT).as_posix()
            findings.append(f"{rel}:{exc.lineno or 1}: python-parse-error")
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_logging_call(node):
                continue
            for keyword in node.keywords:
                if keyword.arg != "extra" or not isinstance(keyword.value, ast.Dict):
                    continue
                for key_node in keyword.value.keys:
                    key = _string_key(key_node)
                    if key and SENSITIVE_LOG_KEY_PATTERN.search(key):
                        findings.append(f"{rel}:{node.lineno}: unsafe-log-extra:{key}")
    return findings


def main() -> int:
    paths = [path for path in _git_paths() if path.is_file() and _is_scannable(path)]
    findings = _scan_secret_patterns(paths) + _scan_logging_extras(paths)
    if findings:
        for finding in findings:
            print(finding)
        return 1
    print("SECRET_SCAN_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
