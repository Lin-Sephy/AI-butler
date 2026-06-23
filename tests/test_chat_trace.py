import json

from core.chat_trace import (
    clip_text,
    compact_json,
    context_summary,
    new_trace_id,
)


def test_new_trace_id_contains_prefix_date_and_user_hint():
    trace_id = new_trace_id("12345678-abcd")

    assert trace_id.startswith("trace_")
    assert "_12345678_" in trace_id


def test_clip_text_truncates_long_text():
    out = clip_text("abcdef", limit=3)

    assert out.startswith("abc")
    assert "truncated 3 chars" in out


def test_compact_json_clips_nested_strings_and_stays_serializable():
    data = {"a": "x" * 10, "items": [{"b": "y" * 8}]}
    compacted = compact_json(data, text_limit=4)

    assert compacted["a"].startswith("xxxx")
    assert compacted["items"][0]["b"].startswith("yyyy")
    json.dumps(compacted, ensure_ascii=False)


def test_context_summary_records_presence_and_excerpts():
    summary = context_summary(
        user_memo="memo",
        ai_memo="ai",
        daily_memo="daily",
        chat_handoff_summary="handoff",
        history_count=3,
        task_day_changed=True,
        switched_to_chat=True,
    )

    assert summary["history_count"] == 3
    assert summary["has_user_memo"] is True
    assert summary["has_ai_memo"] is True
    assert summary["has_daily_memo"] is True
    assert summary["has_chat_handoff"] is True
    assert summary["task_day_changed"] is True
    assert summary["switched_to_chat"] is True
