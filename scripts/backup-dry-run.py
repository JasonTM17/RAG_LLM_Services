"""Validate the backup plan without reading or exporting user data."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILES = ("api", "worker", "web", "observability", "container-observability")
REQUIRED_SERVICES = {
    "api",
    "worker",
    "web",
    "postgres",
    "redis",
    "minio",
    "minio-create-bucket",
    "n8n",
    "prometheus",
    "grafana",
}
REQUIRED_VOLUMES = {
    "postgres_data",
    "redis_data",
    "minio_data",
    "n8n_data",
    "prometheus_data",
    "grafana_data",
}


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


def _require_names(kind: str, actual: set[str], expected: set[str]) -> None:
    missing = expected - actual
    if missing:
        raise RuntimeError(f"missing compose {kind}: {', '.join(sorted(missing))}")


def main() -> int:
    config = _compose_config()
    _require_names("services", set(config.get("services", {})), REQUIRED_SERVICES)
    _require_names("volumes", set(config.get("volumes", {})), REQUIRED_VOLUMES)

    plan = {
        "status": "PASS",
        "mode": "dry-run",
        "data_read": False,
        "backup_domains": [
            {
                "domain": "postgres",
                "volume": "postgres_data",
                "artifact": "logical pg_dump archive",
                "dry_run_command": "docker compose exec -T postgres pg_dump -Fc ...",
            },
            {
                "domain": "minio",
                "volume": "minio_data",
                "artifact": "object storage bucket mirror",
                "dry_run_command": "docker compose exec -T minio mc mirror ...",
            },
            {
                "domain": "n8n",
                "volume": "n8n_data",
                "artifact": "runtime volume plus source-controlled workflow exports",
                "dry_run_command": "docker compose cp n8n:/home/node/.n8n ...",
            },
            {
                "domain": "grafana",
                "volume": "grafana_data",
                "artifact": "runtime volume plus provisioning files",
                "dry_run_command": "docker compose cp grafana:/var/lib/grafana ...",
            },
            {
                "domain": "prometheus",
                "volume": "prometheus_data",
                "artifact": "optional time-series snapshot",
                "dry_run_command": "docker compose cp prometheus:/prometheus ...",
            },
        ],
        "external_requirements": [
            ".env or secret-manager values are backed up outside Git",
            "backup artifacts are encrypted at rest before leaving the host",
            "restores are rehearsed into an isolated environment before release",
        ],
    }
    print(json.dumps(plan, indent=2, sort_keys=True))
    print("BACKUP_DRY_RUN_PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"BACKUP_DRY_RUN_FAIL: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from exc
