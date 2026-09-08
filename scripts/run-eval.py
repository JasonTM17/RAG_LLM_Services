"""Run the default fixture-safe RAG evaluation."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from evals.runner import DEFAULT_DATASET_PATH, DEFAULT_REPORTS_DIR, run_evaluation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(os.getenv("EVAL_DATASET_PATH", str(DEFAULT_DATASET_PATH))),
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=Path(os.getenv("EVAL_REPORTS_DIR", str(DEFAULT_REPORTS_DIR))),
    )
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--no-report", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_evaluation(
        dataset_path=args.dataset,
        reports_dir=args.reports_dir,
        top_k=args.top_k,
        write_report=not args.no_report,
    )
    print(f"EVAL_STATUS={result.status}")
    print(f"EVAL_DATASET={result.dataset_name}")
    print(f"EVAL_EXAMPLES={result.example_count}")
    print(f"EVAL_TOP_K={result.top_k}")
    for metric_name, value in sorted(result.metrics.items()):
        print(f"EVAL_METRIC_{metric_name.upper()}={value}")
    if result.report_json_path is not None:
        print(f"EVAL_REPORT_JSON={result.report_json_path}")
    if result.report_markdown_path is not None:
        print(f"EVAL_REPORT_MARKDOWN={result.report_markdown_path}")
    if result.failures:
        for failure in result.failures:
            print(f"EVAL_FAILURE={failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
