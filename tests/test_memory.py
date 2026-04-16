"""纯逻辑单测：memory 的计算部分（_maybe_promote / _apply_decay / _extract_keywords）。

这些函数不触 DB，只对传入的 dict/list 做运算。
"""

from datetime import timedelta

from core.memory import (
    _maybe_promote, _apply_decay, _extract_keywords,
    CONFIRM_THRESHOLD, CONFIRM_MIN_DAYS,
    DRAFT_EXPIRE_DAYS, CONFIRMED_DECAY_DAYS, HIGH_FREQ_THRESHOLD,
)
from db.database import now_cn


# ---- _maybe_promote ----

class TestMaybePromote:
    def _draft(self, count=1, days_count=1):
        return {
            "content": "test",
            "level": "draft",
            "count": count,
            "trigger_days": [f"d{i}" for i in range(days_count)],
            "updated_at": "2026-04-16 10:00",
            "promoted_at": None,
        }

    def test_confirmed_not_promoted_again(self):
        imp = self._draft()
        imp["level"] = "confirmed"
        assert _maybe_promote(imp, "2026-04-16 10:00") is False

    def test_below_count_threshold(self):
        imp = self._draft(count=CONFIRM_THRESHOLD - 1, days_count=CONFIRM_MIN_DAYS)
        assert _maybe_promote(imp, "2026-04-16 10:00") is False
        assert imp["level"] == "draft"

    def test_below_days_threshold(self):
        imp = self._draft(count=CONFIRM_THRESHOLD + 2, days_count=CONFIRM_MIN_DAYS - 1)
        assert _maybe_promote(imp, "2026-04-16 10:00") is False
        assert imp["level"] == "draft"

    def test_meets_both_thresholds_promotes(self):
        imp = self._draft(count=CONFIRM_THRESHOLD, days_count=CONFIRM_MIN_DAYS)
        assert _maybe_promote(imp, "2026-04-16 10:00") is True
        assert imp["level"] == "confirmed"
        assert imp["promoted_at"] == "2026-04-16 10:00"


# ---- _apply_decay ----

class TestApplyDecay:
    def _imp(self, level, days_old, count=1):
        now = now_cn()
        updated = (now - timedelta(days=days_old)).strftime("%Y-%m-%d %H:%M")
        return {
            "content": "x",
            "level": level,
            "count": count,
            "updated_at": updated,
            "trigger_days": ["d1"],
        }

    def test_confirmed_fresh_survives(self):
        now = now_cn()
        out = _apply_decay([self._imp("confirmed", days_old=3)], now)
        assert len(out) == 1
        assert out[0]["level"] == "confirmed"

    def test_confirmed_expired_degrades_to_draft(self):
        now = now_cn()
        out = _apply_decay([self._imp("confirmed", days_old=CONFIRMED_DECAY_DAYS + 5)], now)
        assert len(out) == 1
        assert out[0]["level"] == "draft"

    def test_high_freq_confirmed_has_longer_window(self):
        """高频印象（count ≥ 10）享受 30 天窗口，不受 14 天约束。"""
        now = now_cn()
        # 在标准窗口外、高频窗口内
        out = _apply_decay(
            [self._imp("confirmed", days_old=CONFIRMED_DECAY_DAYS + 3,
                       count=HIGH_FREQ_THRESHOLD + 5)],
            now,
        )
        assert out[0]["level"] == "confirmed"

    def test_draft_fresh_survives(self):
        now = now_cn()
        out = _apply_decay([self._imp("draft", days_old=2)], now)
        assert len(out) == 1
        assert out[0]["level"] == "draft"

    def test_draft_expired_removed(self):
        now = now_cn()
        out = _apply_decay([self._imp("draft", days_old=DRAFT_EXPIRE_DAYS + 2)], now)
        assert out == []

    def test_no_updated_at_dropped(self):
        """缺 updated_at 的脏数据直接丢弃，不能让一条缺字段的记录拖垮整表。"""
        now = now_cn()
        out = _apply_decay([{"content": "x", "level": "draft"}], now)
        assert out == []


# ---- _extract_keywords ----

class TestExtractKeywords:
    def test_splits_on_chinese_punctuation(self):
        kws = _extract_keywords("焦虑，完美主义，高强度")
        assert "焦虑" in kws
        assert "完美主义" in kws
        assert "高强度" in kws

    def test_splits_on_space(self):
        kws = _extract_keywords("自律 高效")
        assert "自律" in kws
        assert "高效" in kws

    def test_filters_single_char(self):
        """单字符（包括中文单字和英文单字符）被过滤掉，保留 2 字以上片段。"""
        kws = _extract_keywords("a,b,好,焦虑")
        assert "a" not in kws
        assert "b" not in kws
        assert "好" not in kws
        assert "焦虑" in kws

    def test_empty_input(self):
        assert _extract_keywords("") == []
