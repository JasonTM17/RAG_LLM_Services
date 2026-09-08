"""Validate the restore rehearsal sequence without mutating runtime data."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILES = ("api", "worker", "web", "observability", "container-observability")
REQUIRED_RESTORE_SERVICES = {
    "postgres",
    "minio",
    "n8n",
    "grafana",
    "api",
    "worker",
    "prometheus",
}
REQUIRED_DOC_MARKERS = (
    "## Backup and Restore Dry Runs",
    "make backup-dry-run",
    "make restore-dry-run",
    "release readiness",
)


def _compose_config() -> dict[str, Any]:
    command = ["docker", "compose"]
    for profile in PROFILES:
        command.extend(["--profile", profile])
    command.extend(["config", "--format", "json"])
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("docker compose config failed")
    return json.loads(result.stdout)


def _validate_docs() -> None:
    text = (REPO_ROOT / "docs" / "deployment" / "docker.md").read_text(encoding="utf-8")
    missing = [marker for marker in REQUIRED_DOC_MARKERS if marker not in text]
    if missing:
        raise RuntimeError(f"missing restore documentation marker: {missing[0]}")


def main() -> int:
    config = _compose_config()
    services = set(config.get("services", {}))
    missing = REQUIRED_RESTORE_SERVICES - services
    if missing:
        raise RuntimeError(f"missing compose services: {', '.join(sorted(missing))}")
    _validate_docs()

    plan = {
        "status": "PASS",
        "mode": "dry-run",
        "data_mutated": False,
        "restore_sequence": [
            "freeze release identity and backup artifact checksums",
            "stop write paths: api, worker, n8n, and web",
            "restore Postgres into an isolated database and apply migrations",
            "restore MinIO bucket data before re-enabling ingestion",
            "restore n8n runtime state or re-import source workflow exports",
            "restore Grafana runtime state only when provisioning files are insufficient",
            "start services and run acceptance-demo plus observability checks",
        ],
        "rollback_sequence": [
            "stop newly started services without deleting volumes",
            "restore previous image tags or commit checkout",
            "restore Postgres and MinIO from the last verified backup pair",
            "re-run health, retrieval, citation, metrics, n8n, and Grafana checks",
        ],
    }
    print(json.dumps(plan, indent=2, sort_keys=True))
    print("RESTORE_DRY_RUN_PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"RESTORE_DRY_RUN_FAIL: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from exc
