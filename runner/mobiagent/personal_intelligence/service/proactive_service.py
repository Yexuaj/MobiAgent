"""Minimal proactive suggestions over derived semantic hints."""

from __future__ import annotations

from typing import Any


def build_suggestions(semantic_events: dict[str, Any]) -> list[dict[str, Any]]:
    """Attach and return explainable suggestions from derived hints."""

    derived = semantic_events.get("derived")
    if not isinstance(derived, dict):
        return []

    suggestions: list[dict[str, Any]] = []
    item_lookup = _item_lookup(derived)
    used_time_refs: set[str] = set()
    time_hints_by_event = _items_by_event(derived.get("time_hints"))

    for item in _items(derived.get("todo_candidates")):
        evidence_refs = [item["id"]]
        for time_hint in time_hints_by_event.get(item.get("semantic_event_id"), []):
            evidence_refs.append(time_hint["id"])
            used_time_refs.add(time_hint["id"])
        suggestions.append(
            _suggestion(
                len(suggestions) + 1,
                "todo_reminder",
                f"Detected possible task: {item['text']}",
                evidence_refs,
                item_lookup,
            )
        )

    for item in _items(derived.get("profile_facts")):
        suggestions.append(
            _suggestion(
                len(suggestions) + 1,
                "profile_hint",
                f"Detected profile fact candidate: {item['text']}",
                [item["id"]],
                item_lookup,
            )
        )

    for item in _items(derived.get("time_hints")):
        if item["id"] in used_time_refs:
            continue
        suggestions.append(
            _suggestion(
                len(suggestions) + 1,
                "time_reference",
                f"Detected time reference: {item['text']}",
                [item["id"]],
                item_lookup,
            )
        )

    derived["suggestions"] = suggestions
    return suggestions


def _suggestion(
    index: int,
    kind: str,
    text: str,
    evidence_refs: list[str],
    item_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    semantic_event_ids = _unique_ids(evidence_refs, item_lookup, "semantic_event_id")
    source_event_ids = _unique_ids(evidence_refs, item_lookup, "source_event_id")
    return {
        "id": f"suggestion:{index}",
        "kind": kind,
        "text": text,
        "evidence_refs": evidence_refs,
        "semantic_event_ids": semantic_event_ids,
        "source_event_ids": source_event_ids,
    }


def _item_lookup(derived: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for key in ("todo_candidates", "time_hints", "entities", "profile_facts", "relations"):
        for item in _items(derived.get(key)):
            lookup[item["id"]] = item
    return lookup


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for item in value:
        if (
            isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and isinstance(item.get("text"), str)
            and item["text"]
        ):
            items.append(item)
    return items


def _items_by_event(value: Any) -> dict[str, list[dict[str, Any]]]:
    by_event: dict[str, list[dict[str, Any]]] = {}
    for item in _items(value):
        semantic_event_id = item.get("semantic_event_id")
        if isinstance(semantic_event_id, str):
            by_event.setdefault(semantic_event_id, []).append(item)
    return by_event


def _unique_ids(evidence_refs: list[str], item_lookup: dict[str, dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for evidence_ref in evidence_refs:
        value = item_lookup.get(evidence_ref, {}).get(field)
        if isinstance(value, str) and value and value not in seen:
            values.append(value)
            seen.add(value)
    return values
