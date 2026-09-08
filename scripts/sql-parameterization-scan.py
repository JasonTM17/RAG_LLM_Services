"""Detect obvious unsafe f-string SQL execution patterns."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_SCOPES = ("apps", "packages")


def _python_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    paths = [REPO_ROOT / line for line in result.stdout.splitlines() if line.strip()]
    return [
        path
        for path in paths
        if path.relative_to(REPO_ROOT).parts[0] in PYTHON_SCOPES and path.is_file()
    ]


def _is_execute_call(node: ast.Call) -> bool:
    func = node.func
    return isinstance(func, ast.Attribute) and func.attr == "execute"


def _contains_joined_string(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):
        return True
    return any(isinstance(child, ast.JoinedStr) for child in ast.walk(node))


def main() -> int:
    findings: list[str] = []
    for path in _python_paths():
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        rel = path.relative_to(REPO_ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_execute_call(node):
                for arg in node.args:
                    if _contains_joined_string(arg):
                        findings.append(f"{rel}:{node.lineno}: unsafe-fstring-sql")
    if findings:
        for finding in findings:
            print(finding)
        return 1
    print("SQL_PARAMETERIZATION_SCAN_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
