"""Validate source-controlled n8n workflow exports.

The validator is intentionally schema-light: n8n's full export shape changes
between versions, while this project needs stable invariants around names,
trigger types, endpoint contracts, retry bounds, and no committed credentials.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / "workflows" / "n8n"

SECRET_SHAPED_RE = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|gh[po]_[A-Za-z0-9]{30,}|Bearer\s+[A-Za-z0-9._\-]{20,})"
)
CHAT_ROUTE_RE = re.compile(r"/chat(?:/stream)?(?:['\"?\s}]|$)")

REQUIRED_WORKFLOWS = {
    "document-ingestion-orchestrator.json": {
        "name": "RAG - Document Ingestion Orchestrator",
        "trigger": "n8n-nodes-base.webhook",
        "routes": ("/ingestion-jobs/", "/automation/reports"),
    },
    "scheduled-knowledge-sync.json": {
        "name": "RAG - Scheduled Knowledge Sync",
        "trigger": "n8n-nodes-base.scheduleTrigger",
        "routes": ("/knowledge-bases", "/automation/reports"),
    },
    "nightly-rag-evaluation.json": {
        "name": "RAG - Nightly RAG Evaluation",
        "trigger": "n8n-nodes-base.scheduleTrigger",
        "routes": ("/evaluations", "idempotency_key", "/automation/reports"),
    },
    "daily-study-automation.json": {
        "name": "RAG - Daily Study Automation",
        "trigger": "n8n-nodes-base.scheduleTrigger",
        "routes": ("/study/flashcards", "/automation/reports"),
    },
    "failure-notification.json": {
        "name": "RAG - Failure Notification",
        "trigger": "n8n-nodes-base.errorTrigger",
        "routes": ("/automation/reports", "N8N_NOTIFICATION_WEBHOOK_URL"),
    },
}

NON_RETRYABLE_ROUTES = ("/study/flashcards", "N8N_NOTIFICATION_WEBHOOK_URL")


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for nested in value.values():
            yield from _walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


def _strings(value: Any) -> Iterable[str]:
    for item in _walk(value):
        if isinstance(item, str):
            yield item


def _contains_key(value: Any, key_name: str) -> bool:
    if isinstance(value, dict):
        if key_name in value:
            return True
        return any(_contains_key(nested, key_name) for nested in value.values())
    if isinstance(value, list):
        return any(_contains_key(nested, key_name) for nested in value)
    return False


def _validate_http_retry(path: Path, workflow: dict[str, Any], errors: list[str]) -> None:
    nodes = workflow.get("nodes", [])
    for node in nodes:
        if not isinstance(node, dict) or node.get("type") != "n8n-nodes-base.httpRequest":
            continue
        name = node.get("name") or node.get("id") or "<unnamed>"
        node_text = "\n".join(_strings(node))
        if any(route in node_text for route in NON_RETRYABLE_ROUTES):
            if node.get("retryOnFail") is True:
                errors.append(
                    f"{path.name}: HTTP node {name!r} calls a non-idempotent route and must not retry"
                )
            max_tries = node.get("maxTries", 1)
            if not isinstance(max_tries, int) or max_tries != 1:
                errors.append(
                    f"{path.name}: HTTP node {name!r} calls a non-idempotent route and maxTries must be 1"
                )
            wait_ms = node.get("waitBetweenTries", 1000)
            if not isinstance(wait_ms, int) or wait_ms < 1000 or wait_ms > 60000:
                errors.append(
                    f"{path.name}: HTTP node {name!r} waitBetweenTries must be 1000..60000"
                )
            continue
        if node.get("retryOnFail") is not True:
            errors.append(f"{path.name}: HTTP node {name!r} must set retryOnFail=true")
        max_tries = node.get("maxTries")
        if not isinstance(max_tries, int) or max_tries < 1 or max_tries > 3:
            errors.append(f"{path.name}: HTTP node {name!r} maxTries must be 1..3")
        wait_ms = node.get("waitBetweenTries")
        if not isinstance(wait_ms, int) or wait_ms < 1000 or wait_ms > 60000:
            errors.append(f"{path.name}: HTTP node {name!r} waitBetweenTries must be 1000..60000")


def validate_workflows() -> list[str]:
    errors: list[str] = []
    if not WORKFLOW_DIR.is_dir():
        return [f"Missing workflow directory: {WORKFLOW_DIR}"]

    actual_files = {path.name for path in WORKFLOW_DIR.glob("*.json")}
    expected_files = set(REQUIRED_WORKFLOWS)
    for missing in sorted(expected_files - actual_files):
        errors.append(f"Missing workflow export: {missing}")
    for extra in sorted(actual_files - expected_files):
        errors.append(f"Unexpected workflow export: {extra}")

    for filename, contract in REQUIRED_WORKFLOWS.items():
        path = WORKFLOW_DIR / filename
        if not path.exists():
            continue
        try:
            workflow = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{filename}: invalid JSON: {exc}")
            continue
        if not isinstance(workflow, dict):
            errors.append(f"{filename}: top-level value must be an object")
            continue

        if workflow.get("name") != contract["name"]:
            errors.append(f"{filename}: expected name {contract['name']!r}")
        if workflow.get("active") is not False:
            errors.append(f"{filename}: exports must be inactive by default")
        nodes = workflow.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            errors.append(f"{filename}: nodes must be a non-empty array")
            continue
        node_types = {node.get("type") for node in nodes if isinstance(node, dict)}
        if contract["trigger"] not in node_types:
            errors.append(f"{filename}: missing trigger type {contract['trigger']}")
        if _contains_key(workflow, "credentials"):
            errors.append(f"{filename}: workflow export must not contain credentials")

        all_text = "\n".join(_strings(workflow))
        if SECRET_SHAPED_RE.search(all_text):
            errors.append(f"{filename}: credential-shaped material detected")
        if CHAT_ROUTE_RE.search(all_text):
            errors.append(f"{filename}: n8n workflows must not call synchronous chat routes")
        for route in contract["routes"]:
            if route not in all_text:
                errors.append(f"{filename}: missing required route marker {route}")
        _validate_http_retry(path, workflow, errors)

    return errors


def main() -> int:
    errors = validate_workflows()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("N8N_WORKFLOWS_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
