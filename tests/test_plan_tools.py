"""L1 纯逻辑单测：core/plan_tools.py 的时间解析和统计聚合。

把 DS / 用户传的时间字符串解析成 ISO 格式；验证 query_stats 和数据页高峰时段口径一致。
"""

from datetime import datetime
from unittest.mock import patch

from core.plan_tools import _parse_scheduled_at, _tool_query_stats


# 固定"现在"为某一天，方便断言 HH:MM 补日期的行为
FAKE_NOW = datetime(2026, 4, 23, 14, 30, 0)


class TestParseScheduledAt:
    def test_full_iso_passthrough(self):
        result = _parse_scheduled_at("2026-04-24T09:00:00")
        assert result == "2026-04-24T09:00:00"

    def test_iso_with_timezone(self):
        result = _parse_scheduled_at("2026-04-24T09:00:00+08:00")
        # datetime.fromisoformat 保留 tz；只断言带 +08:00
        assert result is not None
        assert "+08:00" in result

    def test_space_separator(self):
        result = _parse_scheduled_at("2026-04-24 09:00")
        assert result == "2026-04-24T09:00:00"

    def test_slash_separator(self):
        result = _parse_scheduled_at("2026/04/24 09:00")
        assert result == "2026-04-24T09:00:00"

    def test_hhmm_only_fills_today(self):
        with patch("core.plan_tools.now_cn", return_value=FAKE_NOW):
            result = _parse_scheduled_at("09:00")
        assert result == "2026-04-23T09:00:00"

    def test_hhmm_single_digit_hour(self):
        with patch("core.plan_tools.now_cn", return_value=FAKE_NOW):
            result = _parse_scheduled_at("9:00")
        assert result == "2026-04-23T09:00:00"

    def test_invalid_hour_returns_none(self):
        assert _parse_scheduled_at("25:00") is None

    def test_invalid_minute_returns_none(self):
        # 秒位数不对（:0 单位）是 HHMM 正则不匹配然后 ISO 也失败
        assert _parse_scheduled_at("12:7") is None

    def test_garbage_returns_none(self):
        assert _parse_scheduled_at("abc") is None

    def test_empty_string_returns_none(self):
        assert _parse_scheduled_at("") is None

    def test_whitespace_returns_none(self):
        assert _parse_scheduled_at("   ") is None

    def test_none_returns_none(self):
        assert _parse_scheduled_at(None) is None

    def test_non_string_returns_none(self):
        assert _parse_scheduled_at(123) is None


class TestQueryStats:
    def test_focus_peak_uses_cn_minutes_not_start_count(self):
        tasks = [
            {
                "status": "completed",
                "started_at": "2026-05-14T02:05:00Z",  # 北京时间 10 点
                "default_minutes": 5,
                "keyword": "短任务 A",
            },
            {
                "status": "completed",
                "started_at": "2026-05-14T02:40:00Z",  # 北京时间 10 点
                "default_minutes": 8,
                "keyword": "短任务 B",
            },
            {
                "status": "completed",
                "started_at": "2026-05-14T08:00:00Z",  # 北京时间 16 点
                "default_minutes": 90,
                "keyword": "长专注",
            },
        ]

        with patch("core.plan_tools.get_tasks_recent", return_value=tasks):
            result = _tool_query_stats("user-1", {})

        assert result["最常专注时段"][0] == "16:00-17:00 (90分钟)"
