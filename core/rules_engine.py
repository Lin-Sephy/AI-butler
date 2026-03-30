"""规则引擎 v2：守门校验 + 精力值感知 + 兜底回复。

不再生成四路径推荐，只校验 AI 回复是否违反精力规则。
"""

import random

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


def build_fallback(ai_response: dict, energy_level: int) -> str:
    """兜底回复：情绪前缀 + 安全建议。"""
    tags = ai_response.get("state_tags", [])

    prefix = ""
    if "累" in tags or "困" in tags:
        prefix = "感觉到你有点累。"
    elif "烦" in tags or "焦虑" in tags:
        prefix = "听起来你现在心情不太好。"
    elif "抗拒" in tags:
        prefix = "不想动的时候硬撑确实没用。"

    actions = {
        1: "你现在最需要的是休息，先睡一会儿或者出去走走吧。",
        2: "要不先做一件最简单的小事？比如整理一下桌面，5分钟就够。",
        3: "现在精力一般，不如先花10分钟整理一下思路再决定下一步。",
    }

    return f"{prefix}{actions.get(energy_level, '先做一件简单的事热热身吧。')}"


def validate_reply(ai_response: dict, energy_level: int) -> tuple[bool, str]:
    """检查 AI 回复是否违反精力规则。返回 (is_valid, final_reply)。"""
    reply = ai_response.get("reply", "")
    rules = ENERGY_RULES.get(energy_level)

    if not rules:
        return True, reply  # 4-5 档无禁止

    # 精力 1 档：combo A/D 时 reply 必须包含恢复关键词
    if energy_level == 1 and ai_response.get("combo") in ("A", "D"):
        if not any(kw in reply for kw in rules["allow_only"]):
            return False, build_fallback(ai_response, energy_level)

    # 精力 2-3 档：task_keyword 不能命中禁止列表
    if "block" in rules:
        task_kw = ai_response.get("task_keyword", "") or ""
        if any(kw in task_kw for kw in rules["block"]):
            return False, build_fallback(ai_response, energy_level)

    return True, reply


def check_energy_drift(ai_response: dict, current_energy: int) -> tuple[int, bool]:
    """检查 AI 感知的精力是否与系统值偏离。

    返回 (energy_to_use, needs_confirm)。
    """
    suggested = ai_response.get("suggested_energy")

    if suggested is None:
        return current_energy, False

    diff = abs(suggested - current_energy)
    if diff <= 1:
        return current_energy, False  # 正常波动
    else:
        return current_energy, True  # 差距 >= 2，需要用户确认


def should_show_action_buttons(ai_response: dict) -> bool:
    """AI 给出了具体行动关键词时展示 开始/换一个 按钮。"""
    task_kw = ai_response.get("task_keyword")
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
