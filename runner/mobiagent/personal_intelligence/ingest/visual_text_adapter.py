"""Optional visual text providers for Personal Intelligence.

Visual text is disabled by default. Stage 2 only exposes the
``workflow_vlm_qa_output`` provider, which reads text already produced by a
workflow ``vlm_qa`` step and maps it back to the screenshot event that supplied
the image.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runner.mobiagent.personal_intelligence.extract.extract_text import short_text
from runner.mobiagent.personal_intelligence.ingest.semantic_events import TEXT_PROVENANCE_WORKFLOW_VLM_QA
from runner.mobiagent.personal_intelligence.load_workflow_run import WorkflowRunRecord, WorkflowStepRecord

PROVIDER_WORKFLOW_VLM_QA_OUTPUT = "workflow_vlm_qa_output"
VISUAL_TEXT_PROVIDERS = (PROVIDER_WORKFLOW_VLM_QA_OUTPUT,)
_STEP_IMAGE_REF = re.compile(r"\$\{steps\.(?P<step_key>[^.}]+)\.output\.image_path\}")


@dataclass(frozen=True)
class VisualTextInputs:
    """Explicit semantic text inputs produced by an enabled visual provider."""

    text_inputs: dict[str, str]
    text_provenance_inputs: dict[str, dict[str, Any]]


def build_visual_text_inputs(
    record: WorkflowRunRecord,
    raw_events: dict[str, Any],
    *,
    provider: str = PROVIDER_WORKFLOW_VLM_QA_OUTPUT,
    max_events: int | None = None,
    max_chars: int | None = None,
) -> VisualTextInputs:
    """Build explicit text/provenance maps for an enabled visual provider."""

    if provider != PROVIDER_WORKFLOW_VLM_QA_OUTPUT:
        allowed = ", ".join(VISUAL_TEXT_PROVIDERS)
        raise ValueError(f"Unsupported visual text provider {provider!r}; expected one of: {allowed}")

    limit = max_events if isinstance(max_events, int) and max_events >= 0 else None
    text_inputs: dict[str, str] = {}
    provenance_inputs: dict[str, dict[str, Any]] = {}
    raw_index = _raw_event_index(raw_events)

    for step in record.steps:
        if limit is not None and len(text_inputs) >= limit:
            break
        if not _is_vlm_qa_step(step):
            continue

        text, source_field = _workflow_vlm_qa_text(step.output)
        text = _cap_text(text, max_chars)
        if text is None:
            continue

        match = _screenshot_event_match(step, raw_index)
        if match is None:
            continue

        text_inputs[match.source_event_id] = text
        provenance_inputs[match.source_event_id] = {
            "kind": TEXT_PROVENANCE_WORKFLOW_VLM_QA,
            "provider": PROVIDER_WORKFLOW_VLM_QA_OUTPUT,
            "source_field": source_field,
            "source_artifact_id": match.source_artifact_id,
            "synthetic": False,
        }

    return VisualTextInputs(text_inputs=text_inputs, text_provenance_inputs=provenance_inputs)


@dataclass(frozen=True)
class _ScreenshotMatch:
    source_event_id: str
    source_artifact_id: str


def _workflow_vlm_qa_text(output: Any) -> tuple[str | None, str]:
    if not isinstance(output, dict):
        return None, ""

    structured = output.get("structured_output")
    if isinstance(structured, dict):
        text = short_text(structured.get("visible_text"))
        if text is not None:
            return text, "output.structured_output.visible_text"
        for key in ("page_summary", "summary", "response"):
            text = short_text(structured.get(key))
            if text is not None:
                return text, f"output.structured_output.{key}"

    for key in ("page_summary", "summary", "response"):
        text = short_text(output.get(key))
        if text is not None:
            return text, f"output.{key}"
    return None, ""


def _cap_text(text: str | None, max_chars: int | None) -> str | None:
    if text is None:
        return None
    if isinstance(max_chars, int) and max_chars >= 0:
        return short_text(text[:max_chars])
    return text


def _is_vlm_qa_step(step: WorkflowStepRecord) -> bool:
    return _tool_name(step.raw_step) == "vlm_qa" or _tool_name(step.output) == "vlm_qa"


def _tool_name(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("tool_name", "tool"):
        tool_name = value.get(key)
        if isinstance(tool_name, str):
            return tool_name
    output = value.get("output")
    if isinstance(output, dict):
        return _tool_name(output)
    return None


def _screenshot_event_match(
    step: WorkflowStepRecord,
    raw_index: dict[str, dict[str, Any]],
) -> _ScreenshotMatch | None:
    source_event_id = _event_id_from_vlm_image(step)
    if source_event_id is not None:
        match = _first_screenshot_artifact(raw_index.get(source_event_id))
        if match is not None:
            return match

    image_value = _vlm_image_value(step)
    if image_value is not None:
        match = _match_artifact_by_image(raw_index, image_value)
        if match is not None:
            return match

    return _previous_screenshot_event(step, raw_index)


def _event_id_from_vlm_image(step: WorkflowStepRecord) -> str | None:
    image_value = _vlm_image_value(step)
    if not isinstance(image_value, str):
        return None
    match = _STEP_IMAGE_REF.fullmatch(image_value.strip())
    if match is None:
        return None
    return f"step:{match.group('step_key')}"


def _vlm_image_value(step: WorkflowStepRecord) -> Any:
    for container in (step.raw_step, step.output):
        value = _nested_image_value(container)
        if value is not None:
            return value
    return None


def _nested_image_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return None
    for key in ("inputs", "input"):
        nested = value.get(key)
        if isinstance(nested, dict) and nested.get("image") is not None:
            return nested.get("image")
    for key in ("image", "image_path", "source_image"):
        if value.get(key) is not None:
            return value.get(key)
    return None


def _raw_event_index(raw_events: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for event in raw_events.get("events", []):
        if isinstance(event, dict) and event.get("event_id") is not None:
            index[str(event["event_id"])] = event
    return index


def _first_screenshot_artifact(event: dict[str, Any] | None) -> _ScreenshotMatch | None:
    if not isinstance(event, dict):
        return None
    source_event_id = str(event.get("event_id") or "")
    for artifact in event.get("artifacts", []):
        if _is_screenshot_artifact(artifact):
            return _ScreenshotMatch(source_event_id, str(artifact["artifact_id"]))
    return None


def _match_artifact_by_image(raw_index: dict[str, dict[str, Any]], image_value: Any) -> _ScreenshotMatch | None:
    image_text = str(image_value)
    image_path = _posix(image_text)
    image_name = Path(image_text).name
    for event in raw_index.values():
        source_event_id = str(event.get("event_id") or "")
        for artifact in event.get("artifacts", []):
            if not _is_screenshot_artifact(artifact):
                continue
            artifact_path = _posix(str(artifact.get("path") or ""))
            if image_path.endswith(artifact_path) or artifact_path.endswith(image_path) or Path(artifact_path).name == image_name:
                return _ScreenshotMatch(source_event_id, str(artifact["artifact_id"]))
    return None


def _previous_screenshot_event(
    step: WorkflowStepRecord,
    raw_index: dict[str, dict[str, Any]],
) -> _ScreenshotMatch | None:
    try:
        current_key = int(step.step_key)
    except ValueError:
        return None

    candidates: list[tuple[int, _ScreenshotMatch]] = []
    for event_id, event in raw_index.items():
        if not event_id.startswith("step:"):
            continue
        try:
            event_key = int(event_id.split(":", 1)[1])
        except ValueError:
            continue
        if event_key >= current_key:
            continue
        match = _first_screenshot_artifact(event)
        if match is not None:
            candidates.append((event_key, match))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _is_screenshot_artifact(artifact: Any) -> bool:
    return isinstance(artifact, dict) and artifact.get("kind") == "screenshot" and isinstance(artifact.get("artifact_id"), str)


def _posix(path: str) -> str:
    return path.replace("\\", "/")
