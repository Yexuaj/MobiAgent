"""Extract lightweight profile fact candidates."""

from __future__ import annotations

from typing import Any

from runner.mobiagent.personal_intelligence.extract.extract_todos import event_ids, event_text, sentence_spans

FACT_TYPES = {
    "preference": (
        "prefer",
        "like",
        "favorite",
        "would rather",
    ),
    "habit": (
        "usually",
        "often",
        "every day",
        "every week",
        "habit",
    ),
    "interest": (
        "interested in",
        "care about",
        "follow",
    ),
    "project": (
        "project",
        "mvp",
        "milestone",
        "demo",
    ),
    "constraint": (
        "cannot",
        "can't",
        "must not",
        "avoid",
        "only",
        "constraint",
        "deadline",
    ),
}


def extract_profile_facts(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Return profile fact candidates, not final profile conclusions."""

    text = event_text(event)
    semantic_event_id, source_event_id = event_ids(event)
    facts: list[dict[str, Any]] = []
    seen: set[str] = set()

    for sentence, start, end in sentence_spans(text):
        fact_type = _fact_type(sentence)
        if fact_type is None:
            continue
        key = f"{fact_type}:{sentence.lower()}"
        if key in seen:
            continue
        facts.append(
            {
                "id": f"profile:{semantic_event_id}:{len(facts) + 1}",
                "kind": "profile_fact_candidate",
                "fact_type": fact_type,
                "subject": "user",
                "semantic_event_id": semantic_event_id,
                "source_event_id": source_event_id,
                "text": sentence,
                "evidence": {
                    "semantic_event_id": semantic_event_id,
                    "source_event_id": source_event_id,
                    "field": "content.text",
                    "span": [start, end],
                },
            }
        )
        seen.add(key)

    return facts


def _fact_type(sentence: str) -> str | None:
    lowered = sentence.lower()
    for fact_type, keywords in FACT_TYPES.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            return fact_type
    return None
