"""Validate source-controlled Prometheus scrape contracts for Phase 10.

This is intentionally schema-light so the repository does not need a YAML
dependency just to guard the local observability contract. Prometheus itself is
still the runtime parser; this script enforces required jobs, targets, alert
rules, and no sensitive/high-cardinality static labels.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMETHEUS_CONFIG = REPO_ROOT / "infra" / "prometheus" / "prometheus.yml"
ALERTS_CONFIG = REPO_ROOT / "infra" / "prometheus" / "alerts.yml"

FORBIDDEN_LABEL_RE = re.compile(
    r"^\s*(user_id|owner_id|tenant_id|request_id|document_id|version_id|job_id|filename|query|prompt)\s*:",
    re.IGNORECASE | re.MULTILINE,
)
SECRET_SHAPED_RE = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|gh[po]_[A-Za-z0-9]{30,}|Bearer\s+[A-Za-z0-9._\-]{20,})"
)

REQUIRED_JOBS = {
    "rag-api": "host.docker.internal:8000",
    "rag-worker": "worker:9108",
    "n8n": "n8n:5678",
    "postgres-exporter": "postgres-exporter:9187",
    "redis-exporter": "redis-exporter:9121",
    "cadvisor": "cadvisor:8080",
}

REQUIRED_ALERTS = {
    "RagApiHighErrorRate",
    "RagWorkerFailures",
    "RagQueueDepthGrowing",
    "RagLlmProviderFailures",
}


def validate_prometheus_config() -> list[str]:
    """Return validation errors for the local Prometheus contract."""
    errors: list[str] = []
    if not PROMETHEUS_CONFIG.exists():
        errors.append(f"Missing Prometheus config: {PROMETHEUS_CONFIG}")
        return errors
    if not ALERTS_CONFIG.exists():
        errors.append(f"Missing Prometheus alerts config: {ALERTS_CONFIG}")
        return errors

    prometheus_text = PROMETHEUS_CONFIG.read_text(encoding="utf-8")
    alerts_text = ALERTS_CONFIG.read_text(encoding="utf-8")
    combined = prometheus_text + "\n" + alerts_text

    if SECRET_SHAPED_RE.search(combined):
        errors.append("Prometheus config contains credential-shaped material")
    if FORBIDDEN_LABEL_RE.search(combined):
        errors.append("Prometheus config contains a forbidden high-cardinality label")
    if "/etc/prometheus/alerts.yml" not in prometheus_text:
        errors.append("Prometheus config must load /etc/prometheus/alerts.yml")

    for job_name, target in REQUIRED_JOBS.items():
        if f"job_name: {job_name}" not in prometheus_text:
            errors.append(f"Missing scrape job: {job_name}")
        if target not in prometheus_text:
            errors.append(f"Missing scrape target for {job_name}: {target}")

    for alert in sorted(REQUIRED_ALERTS):
        if f"alert: {alert}" not in alerts_text:
            errors.append(f"Missing alert rule: {alert}")

    return errors


def main() -> int:
    errors = validate_prometheus_config()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("PROMETHEUS_CONFIG_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
