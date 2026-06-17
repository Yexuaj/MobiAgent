"""Normalize workflow run records into Personal Intelligence raw events."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from runner.mobiagent.personal_intelligence.load_workflow_run import WorkflowRunRecord, WorkflowStepRecord

SCHEMA_VERSION = "pi.raw_events.v1"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def normalize_workflow_run(
    record: WorkflowRunRecord,
    *,
    include_raw_step: bool = False,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Convert a workflow run record into the pi.raw_events.v1 dictionary."""

    root = _safe_resolve(Path(project_root) if project_root is not None else Path.cwd())
    run_dir = _safe_resolve(record.run_dir)
    artifact_base_path, artifact_base_warning = _project_relative_path(run_dir, root, record.run_dir)
    run_summary_path, run_summary_warning = _summary_path(record.summary_path, run_dir, root)

    raw_events: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_dir.name,
        "run_status": record.run_status,
        "workflow_file": _workflow_file_path(record.workflow_file, root),
        "run_summary_path": run_summary_path,
        "artifact_base": {
            "type": "workflow_run_dir",
            "path": artifact_base_path,
        },
        "context": record.context if record.context is not None else {},
        "events": [],
    }
    if artifact_base_warning:
        raw_events["artifact_base"]["path_warning"] = artifact_base_warning
    if run_summary_warning:
        raw_events["run_summary_path_warning"] = run_summary_warning

    raw_events["events"] = [
        _normalize_step(step, run_dir=run_dir, include_raw_step=include_raw_step) for step in record.steps
    ]
    return raw_events


def count_artifacts(raw_events: dict[str, Any]) -> int:
    """Count artifacts in a normalized raw events dictionary."""

    events = raw_events.get("events")
    if not isinstance(events, list):
        return 0
    return sum(len(event.get("artifacts", [])) for event in events if isinstance(event, dict))


def _normalize_step(
    step: WorkflowStepRecord,
    *,
    run_dir: Path,
    include_raw_step: bool,
) -> dict[str, Any]:
    output = step.output if isinstance(step.output, dict) else {}
    error = step.error
    artifacts = _collect_artifacts(step, output=output, run_dir=run_dir)
    event: dict[str, Any] = {
        "event_id": f"step:{step.step_key}",
        "event_type": "workflow_step",
        "step_id": step.step_id,
        "step_key": step.step_key,
        "status": step.status,
        "started_at": step.started_at,
        "finished_at": step.finished_at,
        "duration_sec": step.duration_sec,
        "artifacts": artifacts,
        "raw_refs": {
            "summary_step_key": step.step_key,
            "has_output": isinstance(step.output, dict) and bool(step.output),
            "has_error": error is not None,
            "output_keys": sorted(str(key) for key in output.keys()),
        },
    }
    if include_raw_step:
        event["raw_step"] = step.raw_step
    return event


def _collect_artifacts(step: WorkflowStepRecord, *, output: dict[str, Any], run_dir: Path) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    image_path = output.get("image_path")
    if image_path:
        artifacts.append(_build_artifact(step.step_key, 1, image_path, "output.image_path", run_dir))
        return artifacts

    step_dir = run_dir / "steps" / step.step_key
    if not step_dir.is_dir():
        return artifacts

    artifact_index = 1
    for candidate in sorted(step_dir.iterdir(), key=lambda path: path.name):
        if candidate.is_file() and candidate.suffix.lower() in IMAGE_EXTENSIONS:
            artifacts.append(_build_artifact(step.step_key, artifact_index, candidate, "step_dir_scan", run_dir))
            artifact_index += 1
    return artifacts


def _build_artifact(
    step_key: str,
    artifact_index: int,
    source_path: str | Path,
    source_field: str,
    run_dir: Path,
) -> dict[str, Any]:
    path_text, warning = _artifact_path(source_path, run_dir)
    artifact: dict[str, Any] = {
        "artifact_id": f"step:{step_key}:artifact:{artifact_index}",
        "kind": "screenshot",
        "path": path_text,
        "source_field": source_field,
        "exists": _path_exists(source_path, run_dir),
    }
    if warning:
        artifact["path_warning"] = warning
    return artifact


def _artifact_path(source_path: str | Path, run_dir: Path) -> tuple[str, str | None]:
    source_text = str(source_path)
    candidate = Path(source_text)
    if candidate.is_absolute():
        relative_path = _try_relative_to(_safe_resolve(candidate), run_dir)
        if relative_path is not None:
            return _posix(relative_path), None
        return _posix(source_text), "artifact path is absolute but not under artifact_base.path"

    return _posix(Path(source_text)), None


def _path_exists(source_path: str | Path, run_dir: Path) -> bool:
    candidate = Path(source_path)
    if not candidate.is_absolute():
        candidate = run_dir / candidate
    try:
        return candidate.exists()
    except OSError:
        return False


def _summary_path(summary_path: Path, run_dir: Path, project_root: Path) -> tuple[str, str | None]:
    resolved_summary = _safe_resolve(summary_path)
    relative_to_run = _try_relative_to(resolved_summary, run_dir)
    if relative_to_run is not None:
        return _posix(relative_to_run), None

    relative_to_project = _try_relative_to(resolved_summary, project_root)
    if relative_to_project is not None:
        return _posix(relative_to_project), "run_summary_path is outside artifact_base.path"

    return _posix(summary_path), "run_summary_path is outside project_root and artifact_base.path"


def _workflow_file_path(workflow_file: Any, project_root: Path) -> Any:
    if not isinstance(workflow_file, str) or not workflow_file:
        return workflow_file

    workflow_path = Path(workflow_file)
    relative_to_project = _try_relative_to(_safe_resolve(workflow_path), project_root)
    if relative_to_project is not None:
        return _posix(relative_to_project)
    return _posix(workflow_file)


def _project_relative_path(path: Path, project_root: Path, original_path: Path) -> tuple[str, str | None]:
    relative_path = _try_relative_to(path, project_root)
    if relative_path is not None:
        return _posix(relative_path), None
    return _posix(original_path), "path is outside project_root"


def _try_relative_to(path: Path, base: Path) -> Path | None:
    try:
        return path.relative_to(base)
    except ValueError:
        return None


def _safe_resolve(path: Path) -> Path:
    try:
        return path.resolve(strict=False)
    except OSError:
        return path.absolute()


def _posix(path: str | Path) -> str:
    return str(path).replace("\\", "/")
