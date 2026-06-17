"""Load MobiAgent workflow run summaries for Personal Intelligence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WorkflowStepRecord:
    """In-memory view of one workflow step from run_summary.json."""

    step_key: str
    step_id: int | None
    status: Any
    started_at: Any
    finished_at: Any
    duration_sec: Any
    output: Any
    error: Any
    raw_step: dict[str, Any]


@dataclass(frozen=True)
class WorkflowRunRecord:
    """In-memory workflow run record used by the raw event normalizer."""

    run_dir: Path
    summary_path: Path
    workflow_file: Any
    run_status: Any
    context: Any
    steps: list[WorkflowStepRecord]


def load_workflow_run(
    run_dir: str | Path | None = None,
    summary_path: str | Path | None = None,
) -> WorkflowRunRecord:
    """Load a workflow run directory or explicit run_summary.json file."""

    if run_dir is None and summary_path is None:
        raise ValueError("Either run_dir or summary_path must be provided.")

    summary_file = Path(summary_path) if summary_path is not None else Path(run_dir) / "run_summary.json"
    effective_run_dir = Path(run_dir) if run_dir is not None else summary_file.parent

    with summary_file.open("r", encoding="utf-8") as file:
        summary = json.load(file)

    if not isinstance(summary, dict):
        raise ValueError(f"Expected summary JSON object in {summary_file}")

    steps = _load_steps(summary.get("steps"))
    return WorkflowRunRecord(
        run_dir=effective_run_dir,
        summary_path=summary_file,
        workflow_file=summary.get("workflow_file"),
        run_status=summary.get("status"),
        context=summary.get("context") if summary.get("context") is not None else {},
        steps=steps,
    )


def _load_steps(raw_steps: Any) -> list[WorkflowStepRecord]:
    if not isinstance(raw_steps, dict):
        return []

    records: list[WorkflowStepRecord] = []
    for step_key, raw_step_value in sorted(raw_steps.items(), key=lambda item: _step_sort_key(str(item[0]))):
        step_key_text = str(step_key)
        raw_step = dict(raw_step_value) if isinstance(raw_step_value, dict) else {"value": raw_step_value}
        records.append(
            WorkflowStepRecord(
                step_key=step_key_text,
                step_id=_to_int_or_none(raw_step.get("step_id", step_key_text)),
                status=raw_step.get("status"),
                started_at=raw_step.get("started_at"),
                finished_at=raw_step.get("finished_at"),
                duration_sec=raw_step.get("duration_sec"),
                output=raw_step.get("output"),
                error=raw_step.get("error"),
                raw_step=raw_step,
            )
        )
    return records


def _step_sort_key(step_key: str) -> tuple[int, int | str]:
    numeric_key = _to_int_or_none(step_key)
    if numeric_key is not None:
        return (0, numeric_key)
    return (1, step_key)


def _to_int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
