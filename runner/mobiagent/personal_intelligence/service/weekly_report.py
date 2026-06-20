"""Markdown report generation from semantic events only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPORT_TITLE = "Personal Intelligence Local Baseline/Debug Report"
REPORT_NOTE = (
    "This report is generated from local baseline extraction for contract validation and demo review. "
    "It is not a final user-facing intelligence report."
)
MAX_SECTION_ITEMS = 5
MAX_RELATION_NOTES = 2


def load_semantic_events(path: str | Path) -> dict[str, Any]:
    """Load a semantic events JSON file."""

    with Path(path).open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"Expected semantic events JSON object in {path}")
    return data


def write_weekly_report(semantic_events: dict[str, Any], out_path: str | Path) -> Path:
    """Write a markdown report from already-derived semantic events."""

    output_path = Path(out_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_weekly_report(semantic_events), encoding="utf-8")
    return output_path


def render_weekly_report(semantic_events: dict[str, Any]) -> str:
    """Render a compact local baseline/debug report."""

    source_run = semantic_events.get("source_run") if isinstance(semantic_events.get("source_run"), dict) else {}
    derived = semantic_events.get("derived") if isinstance(semantic_events.get("derived"), dict) else {}
    events = semantic_events.get("events", [])
    event_count = len(events) if isinstance(events, list) else 0
    todos = _items(derived.get("todo_candidates"))
    time_hints = _items(derived.get("time_hints"))
    profile_facts = _items(derived.get("profile_facts"))
    relations = _items(derived.get("relations"))
    evidence_index: dict[str, tuple[str, dict[str, Any]]] = {}

    lines = [
        f"# {REPORT_TITLE}",
        "",
        REPORT_NOTE,
        "",
    ]

    _highlights(lines, source_run, semantic_events, event_count, todos, time_hints, profile_facts, relations)
    _possible_tasks(lines, todos, time_hints, evidence_index)
    _time_references(lines, time_hints, evidence_index)
    _context_notes(lines, derived, profile_facts, relations, evidence_index)
    _evidence(lines, evidence_index)
    return "\n".join(lines).rstrip() + "\n"


def _highlights(
    lines: list[str],
    source_run: dict[str, Any],
    semantic_events: dict[str, Any],
    event_count: int,
    todos: list[dict[str, Any]],
    time_hints: list[dict[str, Any]],
    profile_facts: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> None:
    lines.append("## Highlights")
    lines.append(f"- Run: `{source_run.get('run_id', 'unknown')}`")
    lines.append(f"- Schema: `{semantic_events.get('schema_version', 'unknown')}`")
    lines.append(f"- Events reviewed: {event_count}")
    lines.append(
        f"- Derived summary: {len(todos)} possible task(s), "
        f"{len(time_hints)} time reference(s), {len(profile_facts)} context note(s)"
    )
    lines.append(f"- Relation links retained in semantic JSON: {len(relations)}")
    lines.append("")


def _possible_tasks(
    lines: list[str],
    todos: list[dict[str, Any]],
    time_hints: list[dict[str, Any]],
    evidence_index: dict[str, tuple[str, dict[str, Any]]],
) -> None:
    lines.append("## Possible Tasks")
    if not todos:
        lines.append("- None")
        lines.append("")
        return

    times_by_event = _items_by_event(time_hints)
    for todo in todos[:MAX_SECTION_ITEMS]:
        time_text = _time_suffix(times_by_event.get(str(todo.get("semantic_event_id")), []))
        lines.append(f"- {todo.get('text', '')}{time_text} {_evidence_ref(todo, evidence_index)}")
    lines.append("")


def _time_references(
    lines: list[str],
    time_hints: list[dict[str, Any]],
    evidence_index: dict[str, tuple[str, dict[str, Any]]],
) -> None:
    lines.append("## Time References")
    if not time_hints:
        lines.append("- None")
        lines.append("")
        return

    for item in time_hints[:MAX_SECTION_ITEMS]:
        lines.append(f"- {item.get('text', '')} {_evidence_ref(item, evidence_index)}")
    lines.append("")


def _context_notes(
    lines: list[str],
    derived: dict[str, Any],
    profile_facts: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    evidence_index: dict[str, tuple[str, dict[str, Any]]],
) -> None:
    lines.append("## Context Notes")
    notes: list[str] = []
    for item in profile_facts[:MAX_SECTION_ITEMS]:
        fact_type = item.get("fact_type", "unknown")
        notes.append(f"- {item.get('text', '')} ({fact_type} candidate) {_evidence_ref(item, evidence_index)}")

    item_lookup = _item_lookup(derived)
    for relation in _high_value_relations(relations, item_lookup):
        from_item = item_lookup.get(str(relation.get("from_id")), {})
        to_item = item_lookup.get(str(relation.get("to_id")), {})
        notes.append(
            f"- Task/time link: {from_item.get('text', '')} -> {to_item.get('text', '')} "
            f"{_evidence_ref(relation, evidence_index)}"
        )

    if not notes:
        lines.append("- None")
    else:
        lines.extend(notes[:MAX_SECTION_ITEMS])
    lines.append("")


def _evidence(lines: list[str], evidence_index: dict[str, tuple[str, dict[str, Any]]]) -> None:
    lines.append("## Evidence")
    if not evidence_index:
        lines.append("- None")
        lines.append("")
        return
    for label, item in evidence_index.values():
        lines.append(f"- {label}: {_evidence_text(item)}")
    lines.append("")


def _evidence_text(item: dict[str, Any]) -> str:
    evidence = item.get("evidence")
    if not isinstance(evidence, dict):
        return "Evidence: none"
    span = evidence.get("span")
    return (
        f"Evidence: {evidence.get('semantic_event_id', '')} / {evidence.get('source_event_id', '')} "
        f"span {span}"
    )


def _evidence_ref(item: dict[str, Any], evidence_index: dict[str, tuple[str, dict[str, Any]]]) -> str:
    item_id = item.get("id")
    if not isinstance(item_id, str) or not item_id:
        return "[Evidence: none]"
    if item_id not in evidence_index:
        evidence_index[item_id] = (f"E{len(evidence_index) + 1}", item)
    return f"[{evidence_index[item_id][0]}]"


def _time_suffix(time_hints: list[dict[str, Any]]) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for hint in time_hints:
        text = hint.get("text")
        key = text.lower() if isinstance(text, str) else ""
        if text and key not in seen:
            values.append(text)
            seen.add(key)
    return f" (time: {', '.join(values)})" if values else ""


def _high_value_relations(
    relations: list[dict[str, Any]], item_lookup: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for relation in relations:
        if relation.get("relation_type") != "has_time":
            continue
        if str(relation.get("from_id")) not in item_lookup or str(relation.get("to_id")) not in item_lookup:
            continue
        selected.append(relation)
        if len(selected) >= MAX_RELATION_NOTES:
            break
    return selected


def _item_lookup(derived: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for key in ("todo_candidates", "time_hints", "entities", "profile_facts", "relations"):
        for item in _items(derived.get(key)):
            item_id = item.get("id")
            if isinstance(item_id, str):
                lookup[item_id] = item
    return lookup


def _items_by_event(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_event: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        event_id = item.get("semantic_event_id")
        if isinstance(event_id, str):
            by_event.setdefault(event_id, []).append(item)
    return by_event


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        item
        for item in value
        if isinstance(item, dict) and isinstance(item.get("text"), str) and item.get("text")
    ]
