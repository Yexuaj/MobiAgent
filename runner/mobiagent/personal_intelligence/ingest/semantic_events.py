"""Build the minimal semantic event layer from raw workflow events."""

from __future__ import annotations

from typing import Any

from runner.mobiagent.personal_intelligence.extract.extract_text import short_text
from runner.mobiagent.personal_intelligence.ingest.normalize_events import normalize_workflow_run

SCHEMA_VERSION = "pi.semantic.v1"
TEXT_PROVENANCE_NONE = "none"
TEXT_PROVENANCE_LOCAL_PRIVATE = "local_private"
TEXT_PROVENANCE_SYNTHETIC = "synthetic_fixture"
TEXT_PROVENANCE_KINDS = {
    TEXT_PROVENANCE_NONE,
    TEXT_PROVENANCE_LOCAL_PRIVATE,
    TEXT_PROVENANCE_SYNTHETIC,
}


def build_semantic_events_from_run(
    record: Any,
    *,
    text_provenance: str = TEXT_PROVENANCE_NONE,
    text_inputs: dict[str, str] | None = None,
    text_provenance_inputs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build semantic events from a loaded workflow run record."""

    return build_semantic_events(
        normalize_workflow_run(record),
        text_provenance=text_provenance,
        text_inputs=text_inputs,
        text_provenance_inputs=text_provenance_inputs,
    )


def build_semantic_events(
    raw_events: dict[str, Any],
    *,
    text_provenance: str = TEXT_PROVENANCE_NONE,
    text_inputs: dict[str, str] | None = None,
    text_provenance_inputs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Convert pi.raw_events.v1 data into the pi.semantic.v1 shape."""

    _validate_text_provenance(text_provenance)
    source_run = _source_run(raw_events)
    events = [
        _semantic_event(
            raw_event,
            text_provenance=text_provenance,
            text_inputs=text_inputs or {},
            text_provenance_inputs=text_provenance_inputs or {},
        )
        for raw_event in raw_events.get("events", [])
        if isinstance(raw_event, dict)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "source_run": source_run,
        "events": events,
        "derived": {
            "todo_candidates": [],
            "time_hints": [],
            "entities": [],
            "profile_facts": [],
            "relations": [],
            "suggestions": [],
        },
    }


def _source_run(raw_events: dict[str, Any]) -> dict[str, Any]:
    artifact_base = raw_events.get("artifact_base")
    if isinstance(artifact_base, dict):
        artifact_base_value = {
            "type": artifact_base.get("type"),
            "path": artifact_base.get("path"),
        }
    else:
        artifact_base_value = {
            "type": None,
            "path": None,
        }
    return {
        "run_id": raw_events.get("run_id"),
        "run_status": raw_events.get("run_status"),
        "workflow_file": raw_events.get("workflow_file"),
        "artifact_base": artifact_base_value,
    }


def _semantic_event(
    raw_event: dict[str, Any],
    *,
    text_provenance: str,
    text_inputs: dict[str, str],
    text_provenance_inputs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source_event_id = str(raw_event["event_id"])
    text = _allowed_text(source_event_id, text_inputs, text_provenance)
    provenance_input = _provenance_input(source_event_id, text_provenance_inputs)
    return {
        "semantic_event_id": f"sem:{source_event_id}",
        "source_event_id": source_event_id,
        "event_type": "workflow_step",
        "content": _content(text, text_provenance, provenance_input),
        "artifacts": _artifacts(raw_event.get("artifacts")),
        "metadata": _metadata(raw_event),
    }


def _content(
    text: str | None,
    text_provenance: str,
    provenance_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if text is None:
        return {
            "text": None,
            "provenance": {
                "kind": "empty",
                "synthetic": False,
            },
        }

    provenance_input = provenance_input or {}
    synthetic = provenance_input.get("synthetic")
    if not isinstance(synthetic, bool):
        synthetic = text_provenance == TEXT_PROVENANCE_SYNTHETIC
    kind = provenance_input.get("kind")
    if not isinstance(kind, str) or not kind:
        kind = text_provenance
    source_field = provenance_input.get("source_field")
    if not isinstance(source_field, str) or not source_field:
        source_field = "content.text"

    provenance: dict[str, Any] = {
        "kind": kind,
        "synthetic": synthetic,
        "source_field": source_field,
    }
    for key in ("provider", "source_artifact_id"):
        value = provenance_input.get(key)
        if isinstance(value, str) and value:
            provenance[key] = value

    return {
        "text": text,
        "provenance": provenance,
    }


def _allowed_text(source_event_id: str, text_inputs: dict[str, str], text_provenance: str) -> str | None:
    if text_provenance == TEXT_PROVENANCE_NONE:
        return None

    for key in (source_event_id, f"sem:{source_event_id}"):
        text = short_text(text_inputs.get(key))
        if text is not None:
            return text
    return None


def _provenance_input(
    source_event_id: str,
    text_provenance_inputs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    for key in (source_event_id, f"sem:{source_event_id}"):
        provenance = text_provenance_inputs.get(key)
        if isinstance(provenance, dict):
            return provenance
    return {}


def _validate_text_provenance(text_provenance: str) -> None:
    if text_provenance not in TEXT_PROVENANCE_KINDS:
        allowed = ", ".join(sorted(TEXT_PROVENANCE_KINDS))
        raise ValueError(f"Unsupported text provenance {text_provenance!r}; expected one of: {allowed}")


def _artifacts(raw_artifacts: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_artifacts, list):
        return []

    artifacts: list[dict[str, Any]] = []
    for artifact in raw_artifacts:
        if not isinstance(artifact, dict):
            continue
        slim_artifact = {
            "artifact_id": artifact.get("artifact_id"),
            "kind": artifact.get("kind"),
            "source_field": artifact.get("source_field"),
            "exists": artifact.get("exists"),
        }
        if artifact.get("path_warning") is not None:
            slim_artifact["path_warning"] = artifact.get("path_warning")
        artifacts.append(slim_artifact)
    return artifacts


def _metadata(raw_event: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ("step_id", "status", "started_at"):
        value = raw_event.get(key)
        if value is not None:
            metadata[key] = value
    metadata["raw_action_type"] = _raw_action_type(raw_event)
    return metadata


def _raw_action_type(raw_event: dict[str, Any]) -> str | None:
    raw_refs = raw_event.get("raw_refs")
    output_keys = raw_refs.get("output_keys") if isinstance(raw_refs, dict) else []
    if not isinstance(output_keys, list):
        return None

    keys = {str(key) for key in output_keys}
    if "image_path" in keys:
        return "screenshot"
    if {"start_x", "start_y", "end_x", "end_y"}.issubset(keys):
        return "swipe"
    if "key" in keys:
        return "keyevent"
    if "seconds" in keys:
        return "wait"
    return None
