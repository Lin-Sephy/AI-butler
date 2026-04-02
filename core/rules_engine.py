"""规则引擎 v4：Python 主导任务触发判断 + 守门校验。

核心变化：
- 新增 should_trigger_task()：根据 DS 信号 + 精力 + 任务栏决定是否触发推任务
- 守门校验保留，只在 call_task 结果上做
- check_energy_drift 改用信号里的 energy_impression
"""

import random


# ---- 任务触发判断 ----

def should_trigger_task(signal: dict, energy_level: int, task_board: list[dict]) -> bool:
    """根据 DS 聊天信号 + 精力 + 任务栏，判断是否需要触发第二次调用（推任务）。

    保守策略：不确定时不触发。

    signal 字段：
        - mentioned_activity: 用户提到的事项
        - activity_category: work / rest / life / None
        - user_attitude: wants_help / just_sharing / frustrated / None
    """
    category = signal.get("activity_category")
    attitude = signal.get("user_attitude")

    # 没提到具体事项 → 不触发
    if not signal.get("mentioned_activity"):
        return False

    # 生活行程类 → 不触发（去奶奶家、吃饭、洗澡等）
    if category == "life":
        return False

    # 用户明确想让你帮忙安排 → 触发
    if attitude == "wants_help" and category in ("work", "rest"):
        return True

    # 用户只是在说/告知 → 不触发
    if attitude == "just_sharing":
        return False

    # 用户提到工作/学习但带负面情绪 → 暂不触发（记录，下轮再看）
    # frustrated 状态先接住情绪更重要，不急着推任务
    if attitude == "frustrated":
        return False

    # 其他情况 → 不触发
    return False


def find_matching_task(mentioned_activity: str, task_board: list[dict]) -> dict | None:
    """在任务栏中查找与用户提到的事项匹配的任务。

    用于"做完 xx 了"场景：自动关联到进行中的任务。
    """
    if not mentioned_activity or not task_board:
        return None

    activity = mentioned_activity.lower()
    for task in task_board:
        keyword = (task.get("keyword") or "").lower()
        if not keyword:
            continue
        # 简单匹配：包含关系
        if activity in keyword or keyword in activity:
            return task

    return None


# ---- 精力规则（守门校验用） ----

ENERGY_RULES = {
    1: {
        "allow_only": ["休息", "睡", "散步", "恢复", "放松", "躺", "出去走", "喝水", "吃"],
        "rule": "精力1档只允许恢复动作",
    },
    2: {
        "block": ["写论文", "写报告", "编程", "写代码", "架构", "设计", "分析", "决策", "决定"],
        "rule": "精力2档禁止深度工作",
    },
    3: {
        "block": ["深度专注", "攻克难题", "核心章节", "架构设计", "关键决策"],
        "rule": "精力3档禁止高强度专注任务",
    },
}


def build_fallback(energy_level: int) -> str:
    """兜底回复：安全建议。"""
    actions = {
        1: "你现在最需要的是休息，先睡一会儿或者出去走走吧。",
        2: "要不先做一件最简单的小事？比如整理一下桌面，5分钟就够。",
        3: "现在精力一般，不如先花10分钟整理一下思路再决定下一步。",
    }
    return actions.get(energy_level, "先做一件简单的事热热身吧。")


def validate_reply(task_response: dict, energy_level: int) -> tuple[bool, str]:
    """检查任务推荐是否违反精力规则。返回 (is_valid, final_reply)。

    仅在 call_task 的结果上调用。
    """
    reply = task_response.get("reply", "")
    task_kw = task_response.get("task_keyword", "") or ""
    rules = ENERGY_RULES.get(energy_level)

    if not rules:
        return True, reply  # 4-5 档无禁止

    # 精力 1 档：task_keyword 必须包含恢复关键词
    if energy_level == 1 and task_kw:
        if not any(kw in task_kw for kw in rules["allow_only"]):
            return False, build_fallback(energy_level)

    # 精力 2-3 档：task_keyword 不能命中禁止列表
    if "block" in rules and task_kw:
        if any(kw in task_kw for kw in rules["block"]):
            return False, build_fallback(energy_level)

    return True, reply


def check_energy_drift(signal: dict, current_energy: int) -> tuple[int, bool]:
    """检查 DS 感知的精力是否与系统值偏离。

    返回 (energy_to_use, needs_confirm)。
    """
    suggested = signal.get("energy_impression")

    if suggested is None:
        return current_energy, False

    try:
        suggested = int(suggested)
    except (TypeError, ValueError):
        return current_energy, False

    diff = abs(suggested - current_energy)
    if diff <= 1:
        return current_energy, False  # 正常波动
    else:
        return current_energy, True  # 差距 >= 2，需要用户确认


def should_show_action_buttons(task_response: dict) -> bool:
    """任务推荐给出了具体行动关键词时展示 开始/换一个 按钮。"""
    task_kw = task_response.get("task_keyword")
    return bool(task_kw and str(task_kw).strip())


# ---- "换一个"追问消息池 ----

FOLLOW_UP_MESSAGES = [
    "没关系，是什么让你不想做这个？",
    "好的，跟我说说你现在更想做什么？",
    "不想做就不做。你现在是累了想休息，还是想换件别的事？",
    "收到，那你现在最想做的事是什么？不管是什么都可以说。",
]


def get_follow_up() -> str:
    """获取一条随机追问消息。"""
    return random.choice(FOLLOW_UP_MESSAGES)
