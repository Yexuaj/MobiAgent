"""Explicit short-text inputs for Personal Intelligence.

This module intentionally does not scan raw workflow output, metadata, or
artifact paths. Text enters the semantic layer only through caller-provided
fixture/demo records that map a short string to a known event id.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MAX_TEXT_CHARS = 500


def load_text_fixture(path: str | Path) -> dict[str, str]:
    """Load explicit short text mapped by event id.

    Supported shapes are deliberately small:

    - {"events": [{"source_event_id": "step:1", "content": {"text": "..."}}]}
    - [{"event_id": "step:1", "text": "..."}]
    - {"texts": {"step:1": "..."}}

    The returned mapping may contain source event ids such as ``step:1`` and
    semantic ids such as ``sem:step:1``. No other fields are inspected for text.
    """

    with Path(path).open("r", encoding="utf-8") as file:
        data = json.load(file)

    mapping: dict[str, str] = {}
    if isinstance(data, dict) and isinstance(data.get("texts"), dict):
        for event_id, text in data["texts"].items():
            _add_mapping(mapping, event_id, text)

    records: Any
    if isinstance(data, dict):
        records = data.get("events", [])
    else:
        records = data

    if isinstance(records, list):
        for record in records:
            if isinstance(record, dict):
                _add_record(mapping, record)

    return mapping


def short_text(value: Any) -> str | None:
    """Return a normalized short text value or ``None``."""

    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text:
        return None
    return text[:MAX_TEXT_CHARS]


def _add_record(mapping: dict[str, str], record: dict[str, Any]) -> None:
    text = _record_text(record)
    if text is None:
        return

    for key in ("source_event_id", "semantic_event_id", "event_id"):
        event_id = record.get(key)
        _add_mapping(mapping, event_id, text)


def _record_text(record: dict[str, Any]) -> str | None:
    content = record.get("content")
    if isinstance(content, dict):
        text = short_text(content.get("text"))
        if text is not None:
            return text
    return short_text(record.get("text"))


def _add_mapping(mapping: dict[str, str], event_id: Any, text: Any) -> None:
    normalized = short_text(text)
    if normalized is None or not isinstance(event_id, str) or not event_id:
        return
    mapping[event_id] = normalized
