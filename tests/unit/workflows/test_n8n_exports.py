"""Tests for source-controlled n8n workflow exports."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_DIR = REPO_ROOT / "workflows" / "n8n"

EXPECTED = {
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


def _walk(value: Any):
    yield value
    if isinstance(value, dict):
        for nested in value.values():
            yield from _walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


def _contains_key(value: Any, key_name: str) -> bool:
    return any(isinstance(item, dict) and key_name in item for item in _walk(value))


def _workflow_text(workflow: dict[str, Any]) -> str:
    return json.dumps(workflow, ensure_ascii=False)


def test_validate_n8n_workflows_script_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/validate-n8n-workflows.py"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "N8N_WORKFLOWS_VALID" in result.stdout


def test_all_required_workflow_exports_are_parseable_and_inactive() -> None:
    actual = {path.name for path in WORKFLOW_DIR.glob("*.json")}
    assert actual == set(EXPECTED)

    for filename, contract in EXPECTED.items():
        workflow = json.loads((WORKFLOW_DIR / filename).read_text(encoding="utf-8"))
        assert workflow["name"] == contract["name"]
        assert workflow["active"] is False
        assert isinstance(workflow["nodes"], list)
        assert workflow["nodes"]


def test_workflows_have_required_triggers_and_api_routes() -> None:
    for filename, contract in EXPECTED.items():
        workflow = json.loads((WORKFLOW_DIR / filename).read_text(encoding="utf-8"))
        node_types = {node["type"] for node in workflow["nodes"]}
        text = _workflow_text(workflow)

        assert contract["trigger"] in node_types
        for route in contract["routes"]:
            assert route in text


def test_workflows_do_not_embed_credentials_or_call_chat_routes() -> None:
    for path in WORKFLOW_DIR.glob("*.json"):
        workflow = json.loads(path.read_text(encoding="utf-8"))
        text = _workflow_text(workflow)

        assert not _contains_key(workflow, "credentials")
        assert "/chat" not in text
        assert "Bearer " not in text
        assert "sk-" not in text


def test_http_nodes_use_retry_policy_matching_idempotency() -> None:
    for path in WORKFLOW_DIR.glob("*.json"):
        workflow = json.loads(path.read_text(encoding="utf-8"))
        http_nodes = [
            node for node in workflow["nodes"] if node["type"] == "n8n-nodes-base.httpRequest"
        ]
        assert http_nodes, f"{path.name} should call a bounded HTTP endpoint"
        for node in http_nodes:
            text = _workflow_text(node)
            if "/study/flashcards" in text or "N8N_NOTIFICATION_WEBHOOK_URL" in text:
                assert node.get("retryOnFail") is not True
                assert node.get("maxTries", 1) == 1
                continue
            assert node.get("retryOnFail") is True
            assert 1 <= node.get("maxTries", 0) <= 3
            assert 1000 <= node["waitBetweenTries"] <= 60000
