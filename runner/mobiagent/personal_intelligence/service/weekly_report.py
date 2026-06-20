"""Markdown report generation from semantic events only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
    """Render a compact baseline/debug report for contract validation."""

    source_run = semantic_events.get("source_run") if isinstance(semantic_events.get("source_run"), dict) else {}
    derived = semantic_events.get("derived") if isinstance(semantic_events.get("derived"), dict) else {}
    lines = [
        "# Personal Intelligence Baseline/Debug Report",
        "",
        "This report is for Stage 1 contract validation and leak checks, not a final user-facing report.",
        "",
        f"- Run: `{source_run.get('run_id', 'unknown')}`",
        f"- Schema: `{semantic_events.get('schema_version', 'unknown')}`",
        f"- Events: {len(semantic_events.get('events', [])) if isinstance(semantic_events.get('events'), list) else 0}",
        "",
    ]

    _section(lines, "Todo Candidates", derived.get("todo_candidates"), _item_line)
    _section(lines, "Time Hints", derived.get("time_hints"), _item_line)
    _section(lines, "Entities", derived.get("entities"), _item_line)
    _section(lines, "Profile Fact Candidates", derived.get("profile_facts"), _profile_line)
    _section(lines, "Relation Hints", derived.get("relations"), _relation_line)
    _section(lines, "Proactive Suggestions", derived.get("suggestions"), _suggestion_line)
    return "\n".join(lines).rstrip() + "\n"


def _section(lines: list[str], title: str, value: Any, formatter: Any) -> None:
    lines.append(f"## {title}")
    items = value if isinstance(value, list) else []
    if not items:
        lines.append("- None")
        lines.append("")
        return
    for item in items:
        if isinstance(item, dict):
            lines.append(formatter(item))
    lines.append("")


def _item_line(item: dict[str, Any]) -> str:
    return f"- {item.get('text', '')} (`{item.get('id', '')}`; evidence: {_evidence_text(item)})"


def _profile_line(item: dict[str, Any]) -> str:
    return (
        f"- {item.get('text', '')} "
        f"({item.get('fact_type', 'unknown')} candidate; `{item.get('id', '')}`; evidence: {_evidence_text(item)})"
    )


def _relation_line(item: dict[str, Any]) -> str:
    return (
        f"- {item.get('relation_type', 'unknown')}: `{item.get('from_id', '')}` -> `{item.get('to_id', '')}` "
        f"(`{item.get('id', '')}`; evidence: {_evidence_text(item)})"
    )


def _suggestion_line(item: dict[str, Any]) -> str:
    refs = ", ".join(f"`{ref}`" for ref in item.get("evidence_refs", []) if isinstance(ref, str))
    return f"- {item.get('text', '')} (`{item.get('id', '')}`; evidence refs: {refs})"


def _evidence_text(item: dict[str, Any]) -> str:
    evidence = item.get("evidence")
    if not isinstance(evidence, dict):
        return "`none`"
    span = evidence.get("span")
    return (
        f"`{evidence.get('semantic_event_id', '')}` / `{evidence.get('source_event_id', '')}` "
        f"{evidence.get('field', '')} span {span}"
    )
