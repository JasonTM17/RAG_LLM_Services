"""Validate source-controlled Grafana provisioning and dashboards for Phase 11."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = REPO_ROOT / "infra" / "grafana" / "dashboards"
DATASOURCE_CONFIG = (
    REPO_ROOT / "infra" / "grafana" / "provisioning" / "datasources" / "prometheus.yml"
)
DASHBOARD_PROVIDER_CONFIG = (
    REPO_ROOT / "infra" / "grafana" / "provisioning" / "dashboards" / "rag.yml"
)
COMPOSE_CONFIG = REPO_ROOT / "docker-compose.yml"

PROMETHEUS_UID = "prometheus"
PROMETHEUS_URL = "http://prometheus:9090"
DASHBOARD_PROVISIONING_PATH = "/opt/grafana/dashboards"

SECRET_SHAPED_RE = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|gh[po]_[A-Za-z0-9]{30,}|Bearer\s+[A-Za-z0-9._\-]{20,})"
)
FORBIDDEN_PROMQL_LABEL_RE = re.compile(
    r"\{[^}]*(?:\buser_id\b|\bowner_id\b|\btenant_id\b|\brequest_id\b|"
    r"\bdocument_id\b|\bversion_id\b|\bjob_id\b|\bfilename\b|\bfile_name\b|"
    r"\braw_filename\b|\bquery\b|\braw_query\b|\bprompt\b)\s*(?:=|=~|!=|!~)",
    re.IGNORECASE,
)

REQUIRED_DASHBOARDS: Mapping[str, tuple[str, tuple[str, ...]]] = {
    "rag-system-overview.json": (
        "RAG System Overview",
        (
            "API Request Rate",
            "API Error Rate",
            "HTTP Latency Quantiles",
            "Service Health",
            "Worker Queue Depth",
            "Document Count",
            "Query Count",
        ),
    ),
    "retrieval-performance.json": (
        "Retrieval Performance",
        (
            "Query Rate",
            "Retrieval Latency Quantiles",
            "Vector Search p95",
            "Keyword Search p95",
            "Rerank p95",
            "Retrieved Chunks p95",
        ),
    ),
    "llm-deepseek.json": (
        "LLM / DeepSeek",
        (
            "LLM Request Rate",
            "LLM Failure Rate",
            "LLM Latency Quantiles",
            "Input Tokens",
            "Output Tokens",
            "Estimated LLM Cost",
        ),
    ),
    "ingestion.json": (
        "Ingestion",
        (
            "Indexed Documents",
            "Failed Documents",
            "Ingestion Latency Quantiles",
            "Embedding p95 Latency",
            "Ingestion Chunks",
            "Worker Job Failures",
            "Worker Queue Depth",
        ),
    ),
    "infrastructure.json": (
        "Infrastructure",
        (
            "Postgres Up",
            "Redis Up",
            "Prometheus Targets",
            "Postgres Connections",
            "Redis Memory",
            "Container CPU",
        ),
    ),
    "n8n.json": (
        "n8n",
        (
            "n8n Up",
            "Workflow Success Rate",
            "Workflow Failure Rate",
            "n8n Queue Waiting",
            "n8n Process Memory",
            "n8n CPU",
            "n8n Event Loop Lag",
        ),
    ),
}

REQUIRED_METRIC_FRAGMENTS = frozenset(
    {
        "rag_http_requests_total",
        "rag_http_request_duration_seconds_bucket",
        "rag_queries_total",
        "rag_retrieval_duration_seconds_bucket",
        "rag_vector_search_duration_seconds_bucket",
        "rag_keyword_search_duration_seconds_bucket",
        "rag_rerank_duration_seconds_bucket",
        "rag_retrieved_chunks_bucket",
        "rag_ingestion_documents_total",
        "rag_ingestion_duration_seconds_bucket",
        "rag_ingestion_chunks_total",
        "rag_embedding_duration_seconds_bucket",
        "rag_llm_requests_total",
        "rag_llm_request_duration_seconds_bucket",
        "rag_llm_input_tokens_total",
        "rag_llm_output_tokens_total",
        "rag_llm_estimated_cost_usd_total",
        "rag_worker_jobs_total",
        "rag_worker_queue_depth",
        "up",
        "pg_stat_database_numbackends",
        "redis_memory_used_bytes",
        "container_cpu_usage_seconds_total",
        "n8n_workflow_success_total",
        "n8n_workflow_failed_total",
        "n8n_scaling_mode_queue_jobs_waiting",
    }
)


def _read_text(path: Path, errors: list[str]) -> str:
    if not path.exists():
        errors.append(f"Missing required path: {path.relative_to(REPO_ROOT)}")
        return ""
    return path.read_text(encoding="utf-8")


def _iter_panels(panels: list[object]) -> Iterator[Mapping[str, Any]]:
    for panel in panels:
        if not isinstance(panel, Mapping):
            continue
        yield panel
        nested = panel.get("panels")
        if isinstance(nested, list):
            yield from _iter_panels(nested)


def _panel_exprs(panel: Mapping[str, Any]) -> list[str]:
    exprs: list[str] = []
    targets = panel.get("targets")
    if not isinstance(targets, list):
        return exprs
    for target in targets:
        if isinstance(target, Mapping) and isinstance(target.get("expr"), str):
            exprs.append(target["expr"])
    return exprs


def _datasource_uid(value: object) -> str | None:
    if isinstance(value, Mapping):
        uid = value.get("uid")
        if isinstance(uid, str):
            return uid
    return None


def _validate_dashboard(path: Path, title: str, required_titles: tuple[str, ...]) -> list[str]:
    errors: list[str] = []
    try:
        dashboard = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path.name}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"]

    if not isinstance(dashboard, Mapping):
        return [f"{path.name}: dashboard root must be a JSON object"]
    if dashboard.get("title") != title:
        errors.append(f"{path.name}: expected title {title!r}")
    if not dashboard.get("uid"):
        errors.append(f"{path.name}: missing stable uid")

    panels = dashboard.get("panels")
    if not isinstance(panels, list) or not panels:
        errors.append(f"{path.name}: missing non-empty panels list")
        return errors

    panel_titles: set[str] = set()
    for panel in _iter_panels(panels):
        panel_title = panel.get("title")
        if isinstance(panel_title, str):
            panel_titles.add(panel_title)
        datasource_uid = _datasource_uid(panel.get("datasource"))
        if datasource_uid != PROMETHEUS_UID:
            errors.append(f"{path.name}: panel {panel_title!r} must use datasource uid prometheus")
        exprs = _panel_exprs(panel)
        if not exprs:
            errors.append(f"{path.name}: panel {panel_title!r} must contain a PromQL target")
        for expr in exprs:
            if FORBIDDEN_PROMQL_LABEL_RE.search(expr):
                errors.append(f"{path.name}: panel {panel_title!r} uses a high-cardinality label")
            if "rag_llm_estimated_cost_usd_total" in expr and "Estimated" not in str(panel_title):
                errors.append(f"{path.name}: LLM cost panel title must include Estimated")

    missing_titles = sorted(set(required_titles) - panel_titles)
    if missing_titles:
        errors.append(f"{path.name}: missing required panel titles: {missing_titles}")

    serialized = json.dumps(dashboard, sort_keys=True)
    if SECRET_SHAPED_RE.search(serialized):
        errors.append(f"{path.name}: contains credential-shaped material")
    return errors


def validate_grafana_dashboards() -> list[str]:
    """Return validation errors for Grafana provisioning and dashboards."""
    errors: list[str] = []
    datasource_text = _read_text(DATASOURCE_CONFIG, errors)
    provider_text = _read_text(DASHBOARD_PROVIDER_CONFIG, errors)
    compose_text = _read_text(COMPOSE_CONFIG, errors)

    if datasource_text:
        for expected in (f"uid: {PROMETHEUS_UID}", f"url: {PROMETHEUS_URL}", "isDefault: true"):
            if expected not in datasource_text:
                errors.append(f"Datasource provisioning missing {expected!r}")
        if SECRET_SHAPED_RE.search(datasource_text):
            errors.append("Datasource provisioning contains credential-shaped material")

    if provider_text:
        for expected in (
            "type: file",
            "disableDeletion: true",
            f"path: {DASHBOARD_PROVISIONING_PATH}",
        ):
            if expected not in provider_text:
                errors.append(f"Dashboard provider missing {expected!r}")
        if SECRET_SHAPED_RE.search(provider_text):
            errors.append("Dashboard provider contains credential-shaped material")

    if compose_text:
        for expected in (
            "grafana:",
            "GRAFANA_IMAGE",
            "GRAFANA_PORT",
            "GRAFANA_ADMIN_PASSWORD",
            "./infra/grafana/provisioning:/etc/grafana/provisioning:ro",
            "./infra/grafana/dashboards:/opt/grafana/dashboards:ro",
            "grafana_data:",
            "N8N_METRICS_INCLUDE_QUEUE_METRICS",
        ):
            if expected not in compose_text:
                errors.append(f"docker-compose.yml missing {expected!r}")
        if "GF_SECURITY_ADMIN_PASSWORD: admin" in compose_text:
            errors.append("Grafana compose must not default the admin password to admin")

    combined_promql: list[str] = []
    for filename, (title, required_titles) in REQUIRED_DASHBOARDS.items():
        path = DASHBOARD_DIR / filename
        if not path.exists():
            errors.append(f"Missing dashboard: {path.relative_to(REPO_ROOT)}")
            continue
        errors.extend(_validate_dashboard(path, title, required_titles))
        try:
            dashboard = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        panels = dashboard.get("panels")
        if isinstance(panels, list):
            for panel in _iter_panels(panels):
                combined_promql.extend(_panel_exprs(panel))

    promql_text = "\n".join(combined_promql)
    for metric_fragment in sorted(REQUIRED_METRIC_FRAGMENTS):
        if metric_fragment not in promql_text:
            errors.append(f"Missing dashboard metric fragment: {metric_fragment}")
    return errors


def main() -> int:
    errors = validate_grafana_dashboards()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("GRAFANA_DASHBOARDS_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
