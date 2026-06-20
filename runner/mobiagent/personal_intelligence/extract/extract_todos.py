"""Small rule extractors for todo, time, and entity hints."""

from __future__ import annotations

import re
from typing import Any

from runner.mobiagent.personal_intelligence.extract.extract_time import extract_time_hints
from runner.mobiagent.personal_intelligence.extract.ui_noise_filter import filtered_sentence_spans, sentence_spans

ACTION_PATTERNS = (
    ("remind", re.compile(r"\bremind me to\b", re.IGNORECASE), 0.82),
    ("remember", re.compile(r"\bremember to\b", re.IGNORECASE), 0.8),
    ("need", re.compile(r"\bneeds?\s+to\b", re.IGNORECASE), 0.78),
    ("must", re.compile(r"\bmust\b", re.IGNORECASE), 0.78),
    ("todo", re.compile(r"\bto[- ]?do\b|\btodo\b", re.IGNORECASE), 0.76),
    ("follow_up", re.compile(r"\bfollow\s+up\b", re.IGNORECASE), 0.72),
    ("prepare", re.compile(r"\bprepare\b", re.IGNORECASE), 0.7),
    ("should", re.compile(r"\bshould\b", re.IGNORECASE), 0.62),
    ("remember_zh", re.compile(r"记得"), 0.8),
    ("remind_zh", re.compile(r"提醒我|提醒"), 0.8),
    ("need_zh", re.compile(r"需要|必须"), 0.78),
    ("todo_zh", re.compile(r"待办"), 0.76),
    ("follow_up_zh", re.compile(r"跟进"), 0.72),
    ("prepare_zh", re.compile(r"准备"), 0.7),
)
OBJECT_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*|[\u4e00-\u9fff]+")
TRIM_PUNCTUATION = " \t\r\n:：,，.;；。!！?？-"
NEARBY_TIME_CHARS = 80
LOW_VALUE_OBJECT_TOKENS = {
    "a",
    "an",
    "and",
    "at",
    "for",
    "in",
    "next",
    "on",
    "pm",
    "am",
    "the",
    "today",
    "tomorrow",
    "tonight",
    "week",
}
EXPLICIT_ACTION_TERMS = (
    "need to",
    "needs to",
    "must",
    "todo",
    "to do",
    "remind me to",
    "remember to",
    "需要",
    "必须",
    "待办",
    "提醒",
    "记得",
)
PROFILE_CONTEXT_TERMS = (
    "i prefer",
    "my preference",
    "profile",
    "usually",
    "often",
    "favorite",
    "would rather",
    "我偏好",
    "偏好",
    "通常",
    "经常",
)
PAGE_DESCRIPTION_PATTERNS = (
    re.compile(r"\b(?:this|the|synthetic)?\s*(?:demo|page|screen|dashboard)\s+(?:shows|describes|explains)\b", re.IGNORECASE),
    re.compile(r"\bshows?\s+how\s+to\b", re.IGNORECASE),
)

ENTITY_TERMS = (
    "Android Studio",
    "MobiAgent",
    "Android",
    "WeChat",
    "Chrome",
    "Gmail",
)


def extract_todo_candidates(
    event: dict[str, Any], time_hints: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    text = event_text(event)
    semantic_event_id, source_event_id = event_ids(event)
    event_time_hints = time_hints if time_hints is not None else extract_time_hints(event)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sentence, sentence_start, sentence_end in filtered_sentence_spans(text):
        match = _todo_match(sentence, sentence_start, sentence_end, event_time_hints)
        if match is None or match["text"].lower() in seen:
            continue
        item = build_derived_item(
            "todo",
            "todo_candidate",
            semantic_event_id,
            source_event_id,
            len(candidates) + 1,
            match["text"],
            match["start"],
            match["end"],
        )
        item.update(
            {
                "confidence": match["confidence"],
                "signals": match["signals"],
                "time_hint_refs": match["time_hint_refs"],
            }
        )
        candidates.append(item)
        seen.add(match["text"].lower())
    return candidates


def _todo_match(
    sentence: str,
    sentence_start: int,
    sentence_end: int,
    time_hints: list[dict[str, Any]],
) -> dict[str, Any] | None:
    lowered = sentence.lower()
    if _is_pure_context_sentence(sentence, lowered):
        return None

    for label, pattern, base_confidence in _action_matches(sentence):
        action_start = pattern.start()
        action_end = pattern.end()
        absolute_start = sentence_start + action_start
        candidate_end = _trim_trailing_time(sentence, sentence_start, sentence_end, action_end, time_hints)
        object_text = sentence[action_end : candidate_end - sentence_start]
        object_text = object_text.strip(TRIM_PUNCTUATION)
        if not _has_executable_object(object_text):
            continue
        if _is_preference_or_profile_context(lowered, action_start):
            continue

        local_start, local_end = _trim_local_span(sentence, action_start, candidate_end - sentence_start)
        if local_start >= local_end:
            continue

        absolute_end = sentence_start + local_end
        time_hint_refs = _time_hint_refs(absolute_start, absolute_end, sentence_start, sentence_end, time_hints)
        signals = [f"action:{label}", "object"]
        confidence = base_confidence
        if time_hint_refs:
            signals.append("time_hint")
            confidence += 0.15
        return {
            "text": sentence[local_start:local_end],
            "start": sentence_start + local_start,
            "end": absolute_end,
            "confidence": min(round(confidence, 2), 0.95),
            "signals": signals,
            "time_hint_refs": time_hint_refs,
        }

    return None


def _action_matches(sentence: str) -> list[tuple[str, re.Match[str], float]]:
    matches: list[tuple[str, re.Match[str], float]] = []
    for label, pattern, confidence in ACTION_PATTERNS:
        for match in pattern.finditer(sentence):
            matches.append((label, match, confidence))
    return sorted(matches, key=lambda item: (item[1].start(), -(item[1].end() - item[1].start())))


def _trim_trailing_time(
    sentence: str,
    sentence_start: int,
    sentence_end: int,
    action_end: int,
    time_hints: list[dict[str, Any]],
) -> int:
    candidate_end = sentence_end
    for hint in _same_sentence_time_hints(sentence_start, sentence_end, time_hints):
        span = _span(hint)
        if span is None or span[0] <= sentence_start + action_end:
            continue
        local_time_start = span[0] - sentence_start
        tail = sentence[local_time_start:].strip(TRIM_PUNCTUATION)
        if tail == hint.get("text"):
            candidate_end = min(candidate_end, span[0])
    return candidate_end


def _time_hint_refs(
    todo_start: int,
    todo_end: int,
    sentence_start: int,
    sentence_end: int,
    time_hints: list[dict[str, Any]],
) -> list[str]:
    refs: list[str] = []
    for hint in time_hints:
        hint_id = hint.get("id")
        span = _span(hint)
        if not isinstance(hint_id, str) or span is None:
            continue
        same_sentence = sentence_start <= span[0] and span[1] <= sentence_end
        nearby = _span_distance((todo_start, todo_end), (span[0], span[1])) <= NEARBY_TIME_CHARS
        if (same_sentence or nearby) and hint_id not in refs:
            refs.append(hint_id)
    return refs


def _same_sentence_time_hints(
    sentence_start: int,
    sentence_end: int,
    time_hints: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        hint
        for hint in time_hints
        if (span := _span(hint)) is not None and sentence_start <= span[0] and span[1] <= sentence_end
    ]


def _has_executable_object(text: str) -> bool:
    tokens = [token for token in OBJECT_TOKEN_PATTERN.findall(text) if token.lower() not in LOW_VALUE_OBJECT_TOKENS]
    if not tokens:
        return False
    return any(len(token.strip()) >= 2 or _contains_cjk(token) for token in tokens)


def _is_pure_context_sentence(sentence: str, lowered: str) -> bool:
    if any(pattern.search(sentence) for pattern in PAGE_DESCRIPTION_PATTERNS):
        return not _has_explicit_action_term(lowered)
    if any(term in lowered for term in PROFILE_CONTEXT_TERMS):
        return not _has_explicit_action_term(lowered)
    return False


def _is_preference_or_profile_context(lowered: str, action_start: int) -> bool:
    if _has_explicit_action_term(lowered):
        return False
    for term in PROFILE_CONTEXT_TERMS:
        term_index = lowered.find(term)
        if 0 <= term_index < action_start:
            return True
    return False


def _has_explicit_action_term(lowered: str) -> bool:
    return any(term in lowered for term in EXPLICIT_ACTION_TERMS)


def _trim_local_span(sentence: str, start: int, end: int) -> tuple[int, int]:
    while start < end and sentence[start] in TRIM_PUNCTUATION:
        start += 1
    while end > start and sentence[end - 1] in TRIM_PUNCTUATION:
        end -= 1
    return start, end


def _span(item: dict[str, Any]) -> tuple[int, int] | None:
    evidence = item.get("evidence")
    span = evidence.get("span") if isinstance(evidence, dict) else None
    if (
        isinstance(span, list)
        and len(span) == 2
        and isinstance(span[0], int)
        and isinstance(span[1], int)
    ):
        return span[0], span[1]
    return None


def _span_distance(first: tuple[int, int], second: tuple[int, int]) -> int:
    if first[0] < second[1] and second[0] < first[1]:
        return 0
    if first[1] <= second[0]:
        return second[0] - first[1]
    return first[0] - second[1]


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def extract_entities(event: dict[str, Any]) -> list[dict[str, Any]]:
    text = event_text(event)
    semantic_event_id, source_event_id = event_ids(event)
    entities: list[dict[str, Any]] = []
    used_spans: set[tuple[int, int]] = set()
    for sentence, sentence_start, _sentence_end in filtered_sentence_spans(text):
        sentence_lower = sentence.lower()
        for term in ENTITY_TERMS:
            local_start = sentence_lower.find(term.lower())
            if local_start < 0:
                continue
            start = sentence_start + local_start
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
                    sentence[local_start : local_start + len(term)],
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
