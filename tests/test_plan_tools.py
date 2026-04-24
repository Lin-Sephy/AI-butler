"""L1 纯逻辑单测：core/task_manager.py 的 parse_scheduled_at。

把 DS / 用户传的时间字符串解析成 ISO 格式。原在 plan_tools，重构时移到 task_manager（plan_tools 和 api.py 共用），去掉前导下划线。
"""

from datetime import datetime
from unittest.mock import patch

from core.task_manager import parse_scheduled_at


# 固定"现在"为某一天，方便断言 HH:MM 补日期的行为
FAKE_NOW = datetime(2026, 4, 23, 14, 30, 0)


class TestParseScheduledAt:
    def test_full_iso_passthrough(self):
        result = parse_scheduled_at("2026-04-24T09:00:00")
        assert result == "2026-04-24T09:00:00"

    def test_iso_with_timezone(self):
        result = parse_scheduled_at("2026-04-24T09:00:00+08:00")
        # datetime.fromisoformat 保留 tz；只断言带 +08:00
        assert result is not None
        assert "+08:00" in result

    def test_space_separator(self):
        result = parse_scheduled_at("2026-04-24 09:00")
        assert result == "2026-04-24T09:00:00"

    def test_slash_separator(self):
        result = parse_scheduled_at("2026/04/24 09:00")
        assert result == "2026-04-24T09:00:00"

    def test_hhmm_only_fills_today(self):
        with patch("core.task_manager.now_cn", return_value=FAKE_NOW):
            result = parse_scheduled_at("09:00")
        assert result == "2026-04-23T09:00:00"

    def test_hhmm_single_digit_hour(self):
        with patch("core.task_manager.now_cn", return_value=FAKE_NOW):
            result = parse_scheduled_at("9:00")
        assert result == "2026-04-23T09:00:00"

    def test_invalid_hour_returns_none(self):
        assert parse_scheduled_at("25:00") is None

    def test_invalid_minute_returns_none(self):
        # 秒位数不对（:0 单位）是 HHMM 正则不匹配然后 ISO 也失败
        assert parse_scheduled_at("12:7") is None

    def test_garbage_returns_none(self):
        assert parse_scheduled_at("abc") is None

    def test_empty_string_returns_none(self):
        assert parse_scheduled_at("") is None

    def test_whitespace_returns_none(self):
        assert parse_scheduled_at("   ") is None

    def test_none_returns_none(self):
        assert parse_scheduled_at(None) is None

    def test_non_string_returns_none(self):
        assert parse_scheduled_at(123) is None
