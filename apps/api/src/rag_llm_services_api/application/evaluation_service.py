"""Application service for deterministic RAG evaluation runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from evals.runner import EvaluationThresholds, run_evaluation
from evals.schema import DatasetValidationError, dataset_name_from_path

from rag_llm_services_api.core.config import Settings
from rag_llm_services_api.core.errors import NotFoundError
from rag_llm_services_api.db.models.automation import EvaluationRunModel
from rag_llm_services_api.domain.automation import EvaluationRunStatus
from rag_llm_services_api.infrastructure.repositories.automation import (
    AutomationRepository,
    EvaluationRunCreate,
    EvaluationRunUpdate,
)

REPO_ROOT = Path(__file__).resolve().parents[5]
TERMINAL_STATUSES = {
    EvaluationRunStatus.SUCCEEDED.value,
    EvaluationRunStatus.FAILED.value,
}


@dataclass(frozen=True)
class EvaluationCreateOutcome:
    """Result of creating an evaluation trigger row."""

    run: EvaluationRunModel
    created: bool


@dataclass(frozen=True)
class EvaluationRunOutcome:
    """Result of claiming or executing a worker-side evaluation run."""

    run: EvaluationRunModel
    executed: bool


class EvaluationApplicationService:
    """Create queued evaluation rows and execute them from the worker lane."""

    def __init__(
        self,
        repository: AutomationRepository,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._settings = settings

    async def create_queued(
        self,
        *,
        owner_id: UUID,
        trigger_source: str,
        idempotency_key: str | None,
        workflow_name: str | None,
        dataset_name: str | None,
        metadata: dict[str, Any],
    ) -> EvaluationCreateOutcome:
        """Create an idempotent queued evaluation run without executing it."""
        run, created = await self._repository.create_evaluation_run(
            EvaluationRunCreate(
                owner_id=owner_id,
                trigger_source=trigger_source,
                idempotency_key=idempotency_key,
                workflow_name=workflow_name,
                dataset_name=dataset_name,
                metadata_json=dict(metadata),
            )
        )
        return EvaluationCreateOutcome(run=run, created=created)

    async def mark_running(
        self,
        *,
        owner_id: UUID,
        run_id: UUID,
    ) -> EvaluationRunOutcome:
        """Claim a queued evaluation run and make RUNNING observable."""
        run, claimed = await self._repository.claim_evaluation_run(
            owner_id=owner_id,
            run_id=run_id,
        )
        if run is None:
            raise NotFoundError("Evaluation run not found")
        return EvaluationRunOutcome(run=run, executed=claimed)

    async def complete_running(
        self,
        *,
        owner_id: UUID,
        run_id: UUID,
    ) -> EvaluationRunOutcome:
        """Execute a claimed evaluation run and persist terminal status/result."""
        run = await self._get_run(owner_id=owner_id, run_id=run_id)
        if run.status in TERMINAL_STATUSES and _metadata_result(run.metadata_json) is not None:
            return EvaluationRunOutcome(run=run, executed=False)

        dataset_path = self._resolve_dataset_path(run.dataset_name)
        dataset_name = dataset_name_from_path(dataset_path)

        try:
            result = run_evaluation(
                dataset_path=dataset_path,
                reports_dir=_resolve_repo_path(self._settings.evaluation.reports_dir),
                thresholds=self._thresholds_from_settings(),
                top_k=self._settings.evaluation.top_k,
                write_report=True,
            )
        except DatasetValidationError:
            failed = await self._mark_failed(
                run,
                dataset_name=dataset_name,
                error_message="Evaluation dataset validation failed",
            )
            return EvaluationRunOutcome(run=failed, executed=True)
        except (OSError, ValueError):
            failed = await self._mark_failed(
                run,
                dataset_name=dataset_name,
                error_message="Evaluation execution failed",
            )
            return EvaluationRunOutcome(run=failed, executed=True)

        result_metadata = result.as_metadata()
        metadata = dict(run.metadata_json)
        metadata.update(result_metadata)
        report_path = result_metadata["result"].get("report_json_path")
        completed = await self._repository.update_evaluation_run(
            run,
            EvaluationRunUpdate(
                status=EvaluationRunStatus.SUCCEEDED.value
                if result.status == "PASS"
                else EvaluationRunStatus.FAILED.value,
                dataset_name=dataset_name,
                report_path=report_path if isinstance(report_path, str) else None,
                error_message=None if result.status == "PASS" else "Evaluation thresholds failed",
                metadata_json=metadata,
            ),
        )
        return EvaluationRunOutcome(run=completed, executed=True)

    async def mark_queue_failure(
        self,
        *,
        owner_id: UUID,
        run_id: UUID,
    ) -> EvaluationRunModel:
        """Persist a safe failure when a just-created run cannot be queued."""
        run = await self._get_run(owner_id=owner_id, run_id=run_id)
        dataset_name = run.dataset_name or dataset_name_from_path(self._resolve_dataset_path(None))
        return await self._mark_failed(
            run,
            dataset_name=dataset_name,
            error_message="QueueUnavailable: evaluation task was not queued",
        )

    async def mark_execution_failure(
        self,
        *,
        owner_id: UUID,
        run_id: UUID,
    ) -> EvaluationRunModel:
        """Persist a safe failure when the worker cannot complete a run."""
        run = await self._get_run(owner_id=owner_id, run_id=run_id)
        dataset_name = run.dataset_name or dataset_name_from_path(self._resolve_dataset_path(None))
        return await self._mark_failed(
            run,
            dataset_name=dataset_name,
            error_message="Evaluation execution failed",
        )

    async def _get_run(self, *, owner_id: UUID, run_id: UUID) -> EvaluationRunModel:
        run = await self._repository.get_evaluation_run(owner_id=owner_id, run_id=run_id)
        if run is None:
            raise NotFoundError("Evaluation run not found")
        return run

    def _resolve_dataset_path(self, dataset_name: str | None) -> Path:
        if dataset_name:
            return REPO_ROOT / "evals" / "datasets" / f"{dataset_name}.jsonl"
        return _resolve_repo_path(self._settings.evaluation.dataset_path)

    def _thresholds_from_settings(self) -> EvaluationThresholds:
        cfg = self._settings.evaluation
        return EvaluationThresholds(
            retrieval_hit_rate=cfg.retrieval_hit_rate_threshold,
            recall_at_k=cfg.recall_at_k_threshold,
            mrr=cfg.mrr_threshold,
            ndcg_at_k=cfg.ndcg_at_k_threshold,
            context_relevance=cfg.context_relevance_threshold,
            answer_relevance=cfg.answer_relevance_threshold,
            citation_correctness=cfg.citation_correctness_threshold,
            citation_recall=cfg.citation_recall_threshold,
            faithfulness=cfg.faithfulness_threshold,
        )

    async def _mark_failed(
        self,
        run: EvaluationRunModel,
        *,
        dataset_name: str,
        error_message: str,
    ) -> EvaluationRunModel:
        metadata = dict(run.metadata_json)
        metadata["result"] = {
            "status": "FAIL",
            "dataset_name": dataset_name,
            "example_count": 0,
            "top_k": self._settings.evaluation.top_k,
            "metrics": {},
            "thresholds": self._thresholds_from_settings().as_dict(),
            "failures": [error_message],
            "report_json_path": None,
            "report_markdown_path": None,
        }
        return await self._repository.update_evaluation_run(
            run,
            EvaluationRunUpdate(
                status=EvaluationRunStatus.FAILED.value,
                dataset_name=dataset_name,
                report_path=None,
                error_message=error_message,
                metadata_json=metadata,
            ),
        )


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _metadata_result(metadata_json: dict[str, Any]) -> dict[str, Any] | None:
    result = metadata_json.get("result")
    return result if isinstance(result, dict) else None
