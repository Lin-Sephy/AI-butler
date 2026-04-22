"""纯逻辑单测：规则引擎。无 DB 依赖。"""

from core.rules_engine import (
    should_trigger_task, validate_reply, check_energy_drift,
    should_show_action_buttons,
)


def _sig(**kw):
    """构造一个默认空的 signal，按需覆盖字段。"""
    base = {"mentioned_activity": None, "activity_category": None, "user_attitude": None}
    base.update(kw)
    return base


# ---- should_trigger_task ----

class TestShouldTriggerTask:
    def test_no_activity_mentioned_no_trigger(self):
        assert should_trigger_task(
            _sig(activity_category="work", user_attitude="wants_help"), 4, []
        ) is False

    def test_life_category_never_triggers(self):
        assert should_trigger_task(
            _sig(mentioned_activity="吃饭", activity_category="life",
                 user_attitude="wants_help"), 4, []
        ) is False

    def test_work_wants_help_triggers(self):
        assert should_trigger_task(
            _sig(mentioned_activity="写论文", activity_category="work",
                 user_attitude="wants_help"), 4, []
        ) is True

    def test_work_wants_to_start_triggers(self):
        assert should_trigger_task(
            _sig(mentioned_activity="开始写报告", activity_category="work",
                 user_attitude="wants_to_start"), 4, []
        ) is True

    def test_work_frustrated_no_trigger(self):
        """frustrated 状态先接住情绪，不急着推任务。"""
        assert should_trigger_task(
            _sig(mentioned_activity="写论文", activity_category="work",
                 user_attitude="frustrated"), 4, []
        ) is False

    def test_rest_wants_help_no_trigger(self):
        """v4.1 改动：rest 类不触发推任务。"""
        assert should_trigger_task(
            _sig(mentioned_activity="休息", activity_category="rest",
                 user_attitude="wants_help"), 4, []
        ) is False

    def test_just_sharing_no_trigger(self):
        assert should_trigger_task(
            _sig(mentioned_activity="写论文", activity_category="work",
                 user_attitude="just_sharing"), 4, []
        ) is False


# ---- validate_reply（守门校验） ----

class TestValidateReply:
    def test_high_energy_no_rule(self):
        is_valid, reply = validate_reply(
            {"task_keyword": "写论文", "reply": "走"}, energy_level=5)
        assert is_valid is True
        assert reply == "走"

    def test_energy_1_blocks_non_rest(self):
        is_valid, reply = validate_reply(
            {"task_keyword": "写论文", "reply": "加油"}, energy_level=1)
        assert is_valid is False
        # 兜底里必提"休息"或"走走"
        assert "休息" in reply or "走走" in reply

    def test_energy_1_allows_rest(self):
        is_valid, _ = validate_reply(
            {"task_keyword": "散步", "reply": "好"}, energy_level=1)
        assert is_valid is True

    def test_energy_2_blocks_deep_work(self):
        is_valid, _ = validate_reply(
            {"task_keyword": "写论文", "reply": "加油"}, energy_level=2)
        assert is_valid is False

    def test_energy_2_allows_light(self):
        is_valid, _ = validate_reply(
            {"task_keyword": "整理桌面", "reply": "可"}, energy_level=2)
        assert is_valid is True

    def test_energy_3_blocks_intense_focus(self):
        is_valid, _ = validate_reply(
            {"task_keyword": "深度专注", "reply": "加油"}, energy_level=3)
        assert is_valid is False


# ---- check_energy_drift ----

class TestCheckEnergyDrift:
    def test_no_impression_no_confirm(self):
        e, need = check_energy_drift({"energy_impression": None}, current_energy=4)
        assert e == 4
        assert need is False

    def test_small_diff_no_confirm(self):
        _, need = check_energy_drift({"energy_impression": 3}, current_energy=4)
        assert need is False

    def test_big_diff_needs_confirm(self):
        _, need = check_energy_drift({"energy_impression": 2}, current_energy=4)
        assert need is True

    def test_invalid_impression_ignored(self):
        _, need = check_energy_drift({"energy_impression": "bad"}, current_energy=4)
        assert need is False


# ---- should_show_action_buttons ----

class TestShowActionButtons:
    def test_with_keyword(self):
        assert should_show_action_buttons({"task_keyword": "写论文"}) is True

    def test_empty_keyword(self):
        assert should_show_action_buttons({"task_keyword": ""}) is False

    def test_whitespace_keyword(self):
        assert should_show_action_buttons({"task_keyword": "   "}) is False

    def test_missing_keyword(self):
        assert should_show_action_buttons({}) is False
