"""Validate source-controlled GitHub Actions workflow contracts."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

WORKFLOW_MARKERS = {
    "ci.yml": (
        "actions/checkout@v5",
        "actions/setup-python@v6",
        "astral-sh/setup-uv@v6",
        "pnpm/action-setup@v4",
        "actions/setup-node@v5",
        'RUN_DEEPSEEK_LIVE_TESTS: "false"',
        "uv sync --frozen",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run mypy apps/api/src apps/worker/src packages evals",
        "uv run pytest -q",
        "pnpm install --frozen-lockfile",
        "pnpm web:lint",
        "pnpm web:typecheck",
        "pnpm web:test",
        "pnpm web:build",
        "postgres:",
        "redis:",
        "uv run alembic -c apps/api/alembic.ini upgrade head",
        "uv run python scripts/docs-check.py",
        "docker compose --profile api --profile worker --profile web --profile observability --profile container-observability config --quiet",
    ),
    "container-build.yml": (
        "actions/checkout@v5",
        "docker build --pull -f apps/api/Dockerfile",
        "docker build --pull -f apps/worker/Dockerfile",
        "docker build --pull -f apps/web/Dockerfile",
        "docker compose --profile api --profile worker --profile web --profile observability --profile container-observability config --quiet",
    ),
    "security.yml": (
        "actions/checkout@v5",
        "actions/setup-python@v6",
        "astral-sh/setup-uv@v6",
        "pnpm/action-setup@v4",
        "actions/setup-node@v5",
        "uv run python scripts/secret-scan.py",
        "uv run python scripts/sql-parameterization-scan.py",
        "uv run python scripts/dependency-scan.py",
    ),
    "publish-containers.yml": (
        "actions/checkout@v5",
        "docker/setup-buildx-action@v3",
        "docker/login-action@v3",
        "docker/build-push-action@v6",
        "secrets.DOCKERHUB_USERNAME",
        "secrets.DOCKERHUB_TOKEN",
        "ghcr.io",
    ),
}

SECRET_SHAPED_RE = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|gh[po]_[A-Za-z0-9]{30,}|Bearer\s+[A-Za-z0-9._\-]{20,})"
)


def validate_workflows() -> list[str]:
    errors: list[str] = []
    if not WORKFLOW_DIR.is_dir():
        return [f"missing workflow directory: {WORKFLOW_DIR.relative_to(REPO_ROOT)}"]

    actual = {path.name for path in WORKFLOW_DIR.glob("*.yml")}
    expected = set(WORKFLOW_MARKERS)
    for missing in sorted(expected - actual):
        errors.append(f"missing workflow: {missing}")
    for extra in sorted(actual - expected):
        errors.append(f"unexpected workflow: {extra}")

    for filename, markers in WORKFLOW_MARKERS.items():
        path = WORKFLOW_DIR / filename
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for marker in ("name:", "on:", "permissions:", "jobs:"):
            if marker not in text:
                errors.append(f"{filename}: missing top-level marker {marker}")
        if SECRET_SHAPED_RE.search(text):
            errors.append(f"{filename}: contains credential-shaped material")
        if "secrets.DEEPSEEK_API_KEY" in text or "DEEPSEEK_API_KEY:" in text:
            errors.append(f"{filename}: normal CI path must not require DeepSeek secrets")
        for marker in markers:
            if marker not in text:
                errors.append(f"{filename}: missing required marker {marker!r}")

    return errors


def main() -> int:
    errors = validate_workflows()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("GITHUB_WORKFLOWS_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
