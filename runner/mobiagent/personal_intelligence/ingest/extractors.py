"""Rule-based derived hint extraction for semantic events."""

from __future__ import annotations

from typing import Any

from runner.mobiagent.personal_intelligence.extract.extract_profile import extract_profile_facts
from runner.mobiagent.personal_intelligence.extract.extract_relations import extract_relations
from runner.mobiagent.personal_intelligence.extract.extract_todos import (
    extract_entities,
    extract_time_hints,
    extract_todo_candidates,
)

DERIVED_KEYS = (
    "todo_candidates",
    "time_hints",
    "entities",
    "profile_facts",
    "relations",
    "suggestions",
)


def attach_derived(semantic_events: dict[str, Any]) -> dict[str, Any]:
    """Attach top-level derived hints in place."""

    aggregate: dict[str, list[dict[str, Any]]] = {key: [] for key in DERIVED_KEYS}
    for event in semantic_events.get("events", []):
        if not isinstance(event, dict):
            continue
        derived = extract_event_hints(event)
        for key in ("todo_candidates", "time_hints", "entities", "profile_facts"):
            aggregate[key].extend(derived[key])

    aggregate["relations"] = extract_relations(aggregate)
    semantic_events["derived"] = aggregate
    return semantic_events


def extract_event_hints(event: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Extract event-local hints from explicit semantic text only."""

    time_hints = extract_time_hints(event)
    return {
        "todo_candidates": extract_todo_candidates(event, time_hints=time_hints),
        "time_hints": time_hints,
        "entities": extract_entities(event),
        "profile_facts": extract_profile_facts(event),
    }
