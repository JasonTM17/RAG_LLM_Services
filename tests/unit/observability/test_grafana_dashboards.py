"""Grafana dashboard provisioning contract tests."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate-grafana-dashboards.py"
DASHBOARD_DIR = REPO_ROOT / "infra" / "grafana" / "dashboards"


def _load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_grafana_dashboards", VALIDATOR_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_grafana_dashboard_contract_is_valid() -> None:
    validator = _load_validator()

    assert validator.validate_grafana_dashboards() == []


def test_every_dashboard_uses_prometheus_datasource_uid() -> None:
    for path in sorted(DASHBOARD_DIR.glob("*.json")):
        dashboard = json.loads(path.read_text(encoding="utf-8"))
        for panel in dashboard["panels"]:
            assert panel["datasource"]["uid"] == "prometheus", path.name
            for target in panel["targets"]:
                assert target["datasource"]["uid"] == "prometheus", path.name


def test_estimated_llm_cost_panel_is_explicitly_labeled() -> None:
    dashboard = json.loads((DASHBOARD_DIR / "llm-deepseek.json").read_text(encoding="utf-8"))
    cost_panels = [
        panel
        for panel in dashboard["panels"]
        if any("rag_llm_estimated_cost_usd_total" in target["expr"] for target in panel["targets"])
    ]

    assert cost_panels
    assert all("Estimated" in panel["title"] for panel in cost_panels)
