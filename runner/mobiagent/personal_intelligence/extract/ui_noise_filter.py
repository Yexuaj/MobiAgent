"""Conservative UI-noise filtering for derived extraction inputs."""

from __future__ import annotations

import re

UI_ADDRESS_PHRASES = (
    "search or type web address",
    "search or enter web address",
    "search or type url",
    "address bar",
)

UI_NAV_LABELS = (
    "back",
    "home",
    "tabs",
    "menu",
)

UI_ONLY_TOKENS = {
    "address",
    "android",
    "back",
    "bar",
    "chrome",
    "close",
    "done",
    "forward",
    "home",
    "loading",
    "menu",
    "more",
    "navigation",
    "ok",
    "options",
    "page",
    "recent",
    "refresh",
    "reload",
    "search",
    "settings",
    "status",
    "tab",
    "tabs",
    "type",
    "url",
    "web",
}

USER_SIGNAL_TERMS = (
    "todo",
    "to do",
    "need to",
    "needs to",
    "must",
    "should",
    "prepare",
    "follow up",
    "remind",
    "remember",
    "prefer",
    "like",
    "favorite",
    "usually",
    "often",
    "every day",
    "every week",
    "interested in",
    "care about",
    "project",
    "mvp",
    "milestone",
    "demo",
    "cannot",
    "can't",
    "avoid",
    "deadline",
    "today",
    "tomorrow",
    "tonight",
    "next week",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "今天",
    "明天",
    "今晚",
    "下周",
    "准备",
    "待办",
    "记得",
    "提醒",
    "偏好",
    "喜欢",
    "截止",
    "项目",
    "跟进",
    "必须",
    "应该",
    "需要",
    "不能",
    "不要",
)

URL_OR_HOST_PATTERN = re.compile(
    r"(?:https?://|www\.|localhost\b|(?:\b(?:10\.0\.2\.2|127\.0\.0\.1)\b)|\b\d{1,3}(?:\.\d{1,3}){3}\b)",
    re.IGNORECASE,
)
TOKEN_PATTERN = re.compile(r"[a-z0-9:+%]+", re.IGNORECASE)
STATUS_BAR_PATTERN = re.compile(
    r"^(?:\d{1,2}:\d{2}\s*)?(?:am|pm)?\s*(?:wifi|lte|5g|4g|battery|\d{1,3}%|\d+\s?%)"
    r"(?:\s+(?:wifi|lte|5g|4g|battery|\d{1,3}%|\d+\s?%))*$",
    re.IGNORECASE,
)


def filtered_sentence_spans(text: str) -> list[tuple[str, int, int]]:
    """Return user-meaningful spans into the original text."""

    spans: list[tuple[str, int, int]] = []
    for sentence, start, end in sentence_spans(text):
        if not is_ui_noise_segment(sentence):
            spans.append((sentence, start, end))
    return spans


def sentence_spans(text: str) -> list[tuple[str, int, int]]:
    """Split text into sentence-like spans without breaking URLs or IPs."""

    spans: list[tuple[str, int, int]] = []
    start = 0
    for index, char in enumerate(text):
        if char == "\n" or (char in ".!?" and _is_sentence_boundary(text, index)):
            _append_trimmed_span(spans, text, start, index)
            start = index + 1
    _append_trimmed_span(spans, text, start, len(text))
    return spans


def is_ui_noise_segment(segment: str) -> bool:
    """Return whether a complete segment looks like UI chrome, not user text."""

    normalized = _normalize(segment)
    if not normalized:
        return True
    if has_user_semantic_signal(normalized):
        return False
    if URL_OR_HOST_PATTERN.search(normalized):
        return True
    if normalized in UI_NAV_LABELS or normalized in {"chrome", "android"}:
        return True
    if any(phrase == normalized or phrase in normalized for phrase in UI_ADDRESS_PHRASES):
        return True
    if STATUS_BAR_PATTERN.match(normalized):
        return True

    tokens = TOKEN_PATTERN.findall(normalized)
    if tokens and len(normalized) <= 80 and all(token.lower() in UI_ONLY_TOKENS for token in tokens):
        return True
    return False


def has_user_semantic_signal(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in USER_SIGNAL_TERMS)


def _append_trimmed_span(spans: list[tuple[str, int, int]], text: str, start: int, end: int) -> None:
    raw = text[start:end]
    sentence = raw.strip()
    if not sentence:
        return
    leading = len(raw) - len(raw.lstrip())
    trailing = len(raw.rstrip())
    spans.append((sentence, start + leading, start + trailing))


def _is_sentence_boundary(text: str, index: int) -> bool:
    return index + 1 == len(text) or text[index + 1].isspace()


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())
