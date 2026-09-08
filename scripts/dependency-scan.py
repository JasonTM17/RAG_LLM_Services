"""Run dependency vulnerability scans for the Python and Node workspaces."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], *, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    resolved = shutil.which(command[0])
    if resolved is None:
        return subprocess.CompletedProcess(command, 127, "", f"missing executable: {command[0]}")
    return subprocess.run(
        [resolved, *command[1:]],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _print_failure(name: str, result: subprocess.CompletedProcess[str]) -> None:
    print(f"{name}: FAIL exit={result.returncode}")
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)


def _run_node_audit() -> bool:
    result = _run(["pnpm", "audit", "--prod", "--audit-level", "high", "--json"])
    if result.returncode != 0:
        _print_failure("pnpm-audit", result)
        return False
    data = json.loads(result.stdout or "{}")
    vulnerabilities = data.get("metadata", {}).get("vulnerabilities", {})
    high = int(vulnerabilities.get("high", 0) or 0)
    critical = int(vulnerabilities.get("critical", 0) or 0)
    print(f"pnpm-audit: PASS high={high} critical={critical}")
    return high == 0 and critical == 0


def _run_python_audit() -> bool:
    with tempfile.TemporaryDirectory(prefix="rag-dependency-scan-") as tmp:
        requirements = Path(tmp) / "requirements.txt"
        export = _run(
            [
                "uv",
                "export",
                "--frozen",
                "--all-packages",
                "--no-dev",
                "--no-emit-project",
                "--no-emit-workspace",
                "--no-emit-local",
                "--no-hashes",
                "--output-file",
                str(requirements),
            ]
        )
        if export.returncode != 0:
            _print_failure("uv-export", export)
            return False
        result = _run(
            [
                "uv",
                "tool",
                "run",
                "--from",
                "pip-audit",
                "pip-audit",
                "--requirement",
                str(requirements),
                "--format",
                "json",
            ]
        )
    if result.returncode != 0:
        _print_failure("pip-audit", result)
        return False
    data = json.loads(result.stdout or "{}")
    dependencies = data.get("dependencies", [])
    vulnerabilities = sum(len(dep.get("vulns", [])) for dep in dependencies)
    print(f"pip-audit: PASS vulnerabilities={vulnerabilities}")
    return vulnerabilities == 0


def main() -> int:
    ok = True
    for executable in ("pnpm", "uv"):
        if _run([executable, "--version"]).returncode != 0:
            print(f"{executable}: NOT_RUN missing executable")
            ok = False
    if not ok:
        return 1

    ok = _run_node_audit() and ok
    ok = _run_python_audit() and ok
    if ok:
        print("DEPENDENCY_SCAN_PASS")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
