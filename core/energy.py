"""精力系统：五档定义、静默继承、精力更新接口。"""

from db.database import get_today_energy, get_avg_energy_7d, save_energy

# 五档定义
ENERGY_LEVELS = {
    1: {"label": "耗竭", "color": "red"},
    2: {"label": "低迷", "color": "orange"},
    3: {"label": "一般", "color": "goldenrod"},
    4: {"label": "良好", "color": "green"},
    5: {"label": "巅峰", "color": "darkgreen"},
}

DEFAULT_ENERGY = 4  # 无任何历史数据时的默认值


def get_current_energy() -> dict:
    """获取当前精力状态。优先用今天的记录，否则静默继承。

    返回: {"energy_level": int, "source": str, "label": str, "color": str}
    """
    today = get_today_energy()
    if today:
        level = today["energy_level"]
        source = today["source"]
    else:
        # 静默继承：取过去 7 天均值四舍五入
        avg = get_avg_energy_7d()
        if avg is not None:
            level = max(1, min(5, round(avg)))
            source = "inherited"
        else:
            level = DEFAULT_ENERGY
            source = "inherited"

    info = ENERGY_LEVELS[level]
    return {
        "energy_level": level,
        "source": source,
        "label": info["label"],
        "color": info["color"],
    }


def update_energy(value: int, source: str = "manual") -> dict:
    """手动设置精力值，写入数据库。

    返回: {"energy_level": int, "source": str, "updated_at": str}
    """
    value = max(1, min(5, value))
    result = save_energy(value, source)
    return result
