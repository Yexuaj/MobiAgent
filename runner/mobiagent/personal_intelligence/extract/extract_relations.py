"""Build lightweight relations between derived hints."""

from __future__ import annotations

from typing import Any

RELATION_TYPES = {"has_time", "mentions_entity", "supports_profile_fact"}


def extract_relations(derived: dict[str, Any]) -> list[dict[str, Any]]:
    """Return simple same-event edges between already extracted items."""

    relations: list[dict[str, Any]] = []
    time_by_event = _items_by_event(derived.get("time_hints"))
    entity_by_event = _items_by_event(derived.get("entities"))

    for todo in _items(derived.get("todo_candidates")):
        event_id = todo.get("semantic_event_id")
        for time_hint in time_by_event.get(event_id, []):
            relations.append(_relation("has_time", todo, time_hint, len(relations) + 1))
        for entity in entity_by_event.get(event_id, []):
            relations.append(_relation("mentions_entity", todo, entity, len(relations) + 1))

    for profile_fact in _items(derived.get("profile_facts")):
        event_id = profile_fact.get("semantic_event_id")
        for entity in entity_by_event.get(event_id, []):
            relations.append(
                _relation("supports_profile_fact", entity, profile_fact, len(relations) + 1)
            )

    return relations


def _relation(relation_type: str, from_item: dict[str, Any], to_item: dict[str, Any], index: int) -> dict[str, Any]:
    semantic_event_id = str(from_item.get("semantic_event_id") or to_item.get("semantic_event_id") or "")
    source_event_id = str(from_item.get("source_event_id") or to_item.get("source_event_id") or "")
    span = _combined_span(from_item, to_item)
    return {
        "id": f"relation:{semantic_event_id}:{index}",
        "kind": "relation",
        "relation_type": relation_type,
        "from_id": from_item["id"],
        "to_id": to_item["id"],
        "semantic_event_id": semantic_event_id,
        "source_event_id": source_event_id,
        "text": f"{from_item.get('text', '')} -> {to_item.get('text', '')}",
        "evidence": {
            "semantic_event_id": semantic_event_id,
            "source_event_id": source_event_id,
            "field": "content.text",
            "span": span,
        },
    }


def _combined_span(first: dict[str, Any], second: dict[str, Any]) -> list[int]:
    first_span = _span(first)
    second_span = _span(second)
    if first_span is None:
        return second_span or [0, 0]
    if second_span is None:
        return first_span
    return [min(first_span[0], second_span[0]), max(first_span[1], second_span[1])]


def _span(item: dict[str, Any]) -> list[int] | None:
    evidence = item.get("evidence")
    span = evidence.get("span") if isinstance(evidence, dict) else None
    if (
        isinstance(span, list)
        and len(span) == 2
        and isinstance(span[0], int)
        and isinstance(span[1], int)
    ):
        return span
    return None


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        item
        for item in value
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item.get("semantic_event_id")
    ]


def _items_by_event(value: Any) -> dict[str, list[dict[str, Any]]]:
    by_event: dict[str, list[dict[str, Any]]] = {}
    for item in _items(value):
        by_event.setdefault(str(item.get("semantic_event_id")), []).append(item)
    return by_event
