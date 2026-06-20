"""Small rule extractors for todo, time, and entity hints."""

from __future__ import annotations

import re
from typing import Any

TODO_KEYWORDS = (
    "todo",
    "to do",
    "need to",
    "needs to",
    "must",
    "should",
    "prepare",
    "follow up",
    "remind me to",
)

TIME_PATTERN = re.compile(
    r"\b(?:today|tomorrow|tonight|next week|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
    r"|\b\d{1,2}(?::\d{2})?\s?(?:am|pm)\b"
    r"|\b\d{4}-\d{1,2}-\d{1,2}\b"
    r"|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",
    re.IGNORECASE,
)

ENTITY_TERMS = (
    "Android Studio",
    "MobiAgent",
    "Android",
    "WeChat",
    "Chrome",
    "Gmail",
)


def extract_todo_candidates(event: dict[str, Any]) -> list[dict[str, Any]]:
    text = event_text(event)
    semantic_event_id, source_event_id = event_ids(event)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sentence, sentence_start, sentence_end in sentence_spans(text):
        lowered = sentence.lower()
        todo_text, offset = _todo_text(sentence, lowered)
        if todo_text and todo_text.lower() not in seen:
            start = sentence_start + offset
            candidates.append(
                build_derived_item(
                    "todo",
                    "todo_candidate",
                    semantic_event_id,
                    source_event_id,
                    len(candidates) + 1,
                    todo_text,
                    start,
                    sentence_end,
                )
            )
            seen.add(todo_text.lower())
    return candidates


def extract_time_hints(event: dict[str, Any]) -> list[dict[str, Any]]:
    text = event_text(event)
    semantic_event_id, source_event_id = event_ids(event)
    hints: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in TIME_PATTERN.finditer(text):
        value = match.group(0)
        key = value.lower()
        if key not in seen:
            hints.append(
                build_derived_item(
                    "time",
                    "time_hint",
                    semantic_event_id,
                    source_event_id,
                    len(hints) + 1,
                    value,
                    match.start(),
                    match.end(),
                )
            )
            seen.add(key)
    return hints


def extract_entities(event: dict[str, Any]) -> list[dict[str, Any]]:
    text = event_text(event)
    semantic_event_id, source_event_id = event_ids(event)
    entities: list[dict[str, Any]] = []
    text_lower = text.lower()
    used_spans: set[tuple[int, int]] = set()
    for term in ENTITY_TERMS:
        start = text_lower.find(term.lower())
        if start < 0:
            continue
        span = (start, start + len(term))
        if span in used_spans:
            continue
        entities.append(
            build_derived_item(
                "entity",
                "entity",
                semantic_event_id,
                source_event_id,
                len(entities) + 1,
                text[start : start + len(term)],
                start,
                start + len(term),
            )
        )
        used_spans.add(span)
    return entities


def event_text(event: dict[str, Any]) -> str:
    content = event.get("content")
    if not isinstance(content, dict):
        return ""
    text = content.get("text")
    return text if isinstance(text, str) else ""


def event_ids(event: dict[str, Any]) -> tuple[str, str]:
    return str(event.get("semantic_event_id") or ""), str(event.get("source_event_id") or "")


def sentence_spans(text: str) -> list[tuple[str, int, int]]:
    sentences: list[tuple[str, int, int]] = []
    for match in re.finditer(r"[^.!?\n]+", text):
        raw_sentence = match.group(0)
        sentence = raw_sentence.strip()
        if not sentence:
            continue
        leading = len(raw_sentence) - len(raw_sentence.lstrip())
        trailing = len(raw_sentence.rstrip())
        sentences.append((sentence, match.start() + leading, match.start() + trailing))
    return sentences


def build_derived_item(
    id_prefix: str,
    kind: str,
    semantic_event_id: str,
    source_event_id: str,
    index: int,
    text: str,
    start: int,
    end: int,
) -> dict[str, Any]:
    return {
        "id": f"{id_prefix}:{semantic_event_id}:{index}",
        "kind": kind,
        "semantic_event_id": semantic_event_id,
        "source_event_id": source_event_id,
        "text": text,
        "evidence": {
            "semantic_event_id": semantic_event_id,
            "source_event_id": source_event_id,
            "field": "content.text",
            "span": [start, end],
        },
    }


def _todo_text(sentence: str, lowered: str) -> tuple[str, int]:
    starts = [lowered.find(keyword.lower()) for keyword in TODO_KEYWORDS if keyword.lower() in lowered]
    if not starts:
        return "", 0
    start = min(index for index in starts if index >= 0)
    return sentence[start:].strip(), start
