"""Lightweight chat trace helpers.

Trace is for debugging request flow, not for becoming a second chat history.
Keep values compact and avoid storing full prompt/context by default.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4


DEFAULT_TEXT_LIMIT = 500


def new_trace_id(user_id: str | None = None) -> str:
    """Generate a sortable-ish trace id with a short user hint."""
    date = datetime.now(UTC).strftime("%Y%m%d")
    user_part = (user_id or "anon").replace("-", "")[:8] or "anon"
    return f"trace_{date}_{user_part}_{uuid4().hex[:10]}"


def clip_text(value, limit: int = DEFAULT_TEXT_LIMIT) -> str:
    """Return a compact string representation for trace storage."""
    if value is None:
        return ""
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + f"...[truncated {len(text) - limit} chars]"


def compact_value(value, text_limit: int = DEFAULT_TEXT_LIMIT):
    """Recursively clip strings in JSON-like values."""
    if isinstance(value, str):
        return clip_text(value, text_limit)
    if isinstance(value, list):
        return [compact_value(item, text_limit) for item in value]
    if isinstance(value, dict):
        return {str(k): compact_value(v, text_limit) for k, v in value.items()}
    return value


def compact_json(value, text_limit: int = DEFAULT_TEXT_LIMIT) -> dict | list | str:
    """Make arbitrary values safe-ish for JSONB trace fields."""
    compacted = compact_value(value, text_limit)
    try:
        json.dumps(compacted, ensure_ascii=False, default=str)
        return compacted
    except TypeError:
        return clip_text(compacted, text_limit)


def context_summary(
    *,
    user_memo: str = "",
    ai_memo: str = "",
    daily_memo: str = "",
    task_board: str = "",
    chat_handoff_summary: str = "",
    history_count: int = 0,
    task_day_changed: bool = False,
    switched_to_chat: bool = False,
) -> dict:
    """Summarize injected context without storing full prompt content."""
    return {
        "history_count": history_count,
        "has_user_memo": bool(user_memo.strip()),
        "user_memo_excerpt": clip_text(user_memo, 240) if user_memo.strip() else "",
        "has_ai_memo": bool(ai_memo.strip()),
        "ai_memo_excerpt": clip_text(ai_memo, 500) if ai_memo.strip() else "",
        "has_daily_memo": bool(daily_memo.strip()),
        "daily_memo_excerpt": clip_text(daily_memo, 240) if daily_memo.strip() else "",
        "has_task_board": bool(task_board.strip()),
        "task_board_excerpt": clip_text(task_board, 240) if task_board.strip() else "",
        "has_chat_handoff": bool(chat_handoff_summary.strip()),
        "chat_handoff_excerpt": clip_text(chat_handoff_summary, 300)
        if chat_handoff_summary.strip()
        else "",
        "task_day_changed": task_day_changed,
        "switched_to_chat": switched_to_chat,
    }
