"""Lightweight time hint extraction with conservative normalization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Match

from runner.mobiagent.personal_intelligence.extract.ui_noise_filter import filtered_sentence_spans

ZH_DAY_OFFSETS = {
    "今天": 0,
    "明天": 1,
    "后天": 2,
}
EN_DAY_OFFSETS = {
    "today": 0,
    "tomorrow": 1,
}
ZH_NUMBERS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
}


@dataclass(frozen=True)
class TimeCandidate:
    text: str
    start: int
    end: int
    normalized: list[str]
    time_grain: str
    is_relative: bool
    needs_time_basis: bool
    confidence: float
    priority: int


@dataclass(frozen=True)
class TimeRule:
    pattern: re.Pattern[str]
    parser: Callable[[Match[str]], dict[str, Any] | None]
    priority: int


ZH_DAY_TIME_PATTERN = re.compile(
    r"(?P<day>今天|明天|后天)\s*(?P<meridiem>上午|早上|下午|晚上|中午)?\s*"
    r"(?P<hour>\d{1,2}|十一|十二|一|二|两|三|四|五|六|七|八|九|十)点"
)
ZH_TIME_OF_DAY_PATTERN = re.compile(
    r"(?P<meridiem>上午|早上|下午|晚上|中午)\s*"
    r"(?P<hour>\d{1,2}|十一|十二|一|二|两|三|四|五|六|七|八|九|十)点"
)
ZH_DAY_PATTERN = re.compile(r"(?P<day>今天|明天|后天)")
EN_DAY_TIME_PATTERN = re.compile(
    r"\b(?P<day>today|tomorrow)\s+(?:at\s+)?"
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)\b",
    re.IGNORECASE,
)
EN_TIME_OF_DAY_PATTERN = re.compile(
    r"\b(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)\b",
    re.IGNORECASE,
)
EN_DAY_PATTERN = re.compile(r"\b(?P<day>today|tomorrow)\b", re.IGNORECASE)

TIME_RULES = (
    TimeRule(ZH_DAY_TIME_PATTERN, lambda match: _parse_zh_day_time(match), 100),
    TimeRule(EN_DAY_TIME_PATTERN, lambda match: _parse_en_day_time(match), 95),
    TimeRule(ZH_TIME_OF_DAY_PATTERN, lambda match: _parse_zh_time_of_day(match), 80),
    TimeRule(EN_TIME_OF_DAY_PATTERN, lambda match: _parse_en_time_of_day(match), 75),
    TimeRule(ZH_DAY_PATTERN, lambda match: _parse_zh_day(match), 60),
    TimeRule(EN_DAY_PATTERN, lambda match: _parse_en_day(match), 55),
)


def extract_time_hints(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Return longest non-overlapping time hints from explicit semantic text."""

    text = event_text(event)
    semantic_event_id, source_event_id = event_ids(event)
    hints: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str]] = set()

    for sentence, sentence_start, _sentence_end in filtered_sentence_spans(text):
        for candidate in _select_time_candidates(sentence):
            start = sentence_start + candidate.start
            end = sentence_start + candidate.end
            key = (start, end, candidate.text.lower())
            if key in seen:
                continue
            hints.append(
                _build_time_hint(
                    semantic_event_id,
                    source_event_id,
                    len(hints) + 1,
                    candidate.text,
                    start,
                    end,
                    candidate,
                )
            )
            seen.add(key)

    return hints


def event_text(event: dict[str, Any]) -> str:
    content = event.get("content")
    if not isinstance(content, dict):
        return ""
    text = content.get("text")
    return text if isinstance(text, str) else ""


def event_ids(event: dict[str, Any]) -> tuple[str, str]:
    return str(event.get("semantic_event_id") or ""), str(event.get("source_event_id") or "")


def _select_time_candidates(sentence: str) -> list[TimeCandidate]:
    candidates = _time_candidates(sentence)
    selected: list[TimeCandidate] = []
    occupied: list[tuple[int, int]] = []

    for candidate in sorted(
        candidates,
        key=lambda item: (item.end - item.start, item.priority, -item.start),
        reverse=True,
    ):
        if any(_overlaps((candidate.start, candidate.end), span) for span in occupied):
            continue
        selected.append(candidate)
        occupied.append((candidate.start, candidate.end))

    return sorted(selected, key=lambda item: item.start)


def _time_candidates(sentence: str) -> list[TimeCandidate]:
    candidates: list[TimeCandidate] = []
    for rule in TIME_RULES:
        for match in rule.pattern.finditer(sentence):
            parsed = rule.parser(match)
            if parsed is None:
                continue
            candidates.append(
                TimeCandidate(
                    text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                    normalized=parsed["normalized"],
                    time_grain=parsed["time_grain"],
                    is_relative=parsed["is_relative"],
                    needs_time_basis=parsed["needs_time_basis"],
                    confidence=parsed["confidence"],
                    priority=rule.priority,
                )
            )
    return candidates


def _parse_zh_day_time(match: Match[str]) -> dict[str, Any] | None:
    day = match.group("day")
    hour = _parse_hour(match.group("hour"))
    if day not in ZH_DAY_OFFSETS or hour is None:
        return None

    meridiem = match.group("meridiem") or ""
    normalized = [f"relative_day:{_signed_offset(ZH_DAY_OFFSETS[day])}"]
    if meridiem:
        normalized_hour = _apply_zh_meridiem(hour, meridiem)
        normalized.append(f"time_of_day:{normalized_hour:02d}:00")
        return _parsed(normalized, "day_time", True, True, 0.9)

    normalized.append(f"hour:{hour}")
    return _parsed(normalized, "ambiguous_hour", True, True, 0.62)


def _parse_zh_time_of_day(match: Match[str]) -> dict[str, Any] | None:
    hour = _parse_hour(match.group("hour"))
    if hour is None:
        return None
    normalized_hour = _apply_zh_meridiem(hour, match.group("meridiem"))
    return _parsed([f"time_of_day:{normalized_hour:02d}:00"], "time_of_day", False, True, 0.82)


def _parse_zh_day(match: Match[str]) -> dict[str, Any] | None:
    day = match.group("day")
    if day not in ZH_DAY_OFFSETS:
        return None
    return _parsed([f"relative_day:{_signed_offset(ZH_DAY_OFFSETS[day])}"], "day", True, True, 0.82)


def _parse_en_day_time(match: Match[str]) -> dict[str, Any] | None:
    day = match.group("day").lower()
    hour = _parse_int_hour(match.group("hour"))
    minute = _parse_minute(match.group("minute"))
    if day not in EN_DAY_OFFSETS or hour is None or minute is None:
        return None
    normalized_hour = _apply_en_ampm(hour, match.group("ampm").lower())
    return _parsed(
        [
            f"relative_day:{_signed_offset(EN_DAY_OFFSETS[day])}",
            f"time_of_day:{normalized_hour:02d}:{minute:02d}",
        ],
        "day_time",
        True,
        True,
        0.9,
    )


def _parse_en_time_of_day(match: Match[str]) -> dict[str, Any] | None:
    hour = _parse_int_hour(match.group("hour"))
    minute = _parse_minute(match.group("minute"))
    if hour is None or minute is None:
        return None
    normalized_hour = _apply_en_ampm(hour, match.group("ampm").lower())
    return _parsed(
        [f"time_of_day:{normalized_hour:02d}:{minute:02d}"],
        "time_of_day",
        False,
        True,
        0.82,
    )


def _parse_en_day(match: Match[str]) -> dict[str, Any] | None:
    day = match.group("day").lower()
    if day not in EN_DAY_OFFSETS:
        return None
    return _parsed([f"relative_day:{_signed_offset(EN_DAY_OFFSETS[day])}"], "day", True, True, 0.82)


def _parsed(
    normalized: list[str],
    time_grain: str,
    is_relative: bool,
    needs_time_basis: bool,
    confidence: float,
) -> dict[str, Any]:
    return {
        "normalized": normalized,
        "time_grain": time_grain,
        "is_relative": is_relative,
        "needs_time_basis": needs_time_basis,
        "confidence": confidence,
    }


def _build_time_hint(
    semantic_event_id: str,
    source_event_id: str,
    index: int,
    text: str,
    start: int,
    end: int,
    candidate: TimeCandidate,
) -> dict[str, Any]:
    return {
        "id": f"time:{semantic_event_id}:{index}",
        "kind": "time_hint",
        "semantic_event_id": semantic_event_id,
        "source_event_id": source_event_id,
        "text": text,
        "normalized": candidate.normalized,
        "time_grain": candidate.time_grain,
        "is_relative": candidate.is_relative,
        "needs_time_basis": candidate.needs_time_basis,
        "confidence": candidate.confidence,
        "evidence": {
            "semantic_event_id": semantic_event_id,
            "source_event_id": source_event_id,
            "field": "content.text",
            "span": [start, end],
        },
    }


def _parse_hour(value: str) -> int | None:
    if value.isdigit():
        return _parse_int_hour(value)
    return ZH_NUMBERS.get(value)


def _parse_int_hour(value: str) -> int | None:
    try:
        hour = int(value)
    except ValueError:
        return None
    return hour if 1 <= hour <= 12 else None


def _parse_minute(value: str | None) -> int | None:
    if value is None:
        return 0
    try:
        minute = int(value)
    except ValueError:
        return None
    return minute if 0 <= minute <= 59 else None


def _apply_zh_meridiem(hour: int, meridiem: str) -> int:
    if meridiem in {"下午", "晚上"} and hour < 12:
        return hour + 12
    if meridiem == "中午" and hour < 11:
        return hour + 12
    return hour


def _apply_en_ampm(hour: int, ampm: str) -> int:
    if ampm == "pm" and hour < 12:
        return hour + 12
    if ampm == "am" and hour == 12:
        return 0
    return hour


def _signed_offset(offset: int) -> str:
    return f"+{offset}" if offset >= 0 else str(offset)


def _overlaps(first: tuple[int, int], second: tuple[int, int]) -> bool:
    return first[0] < second[1] and second[0] < first[1]
