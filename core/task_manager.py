"""任务管理：单任务闭环（创建 → 执行 → 暂停 → 完成/放弃）。

v2 多用户改造（2026-04-15）：所有公开函数第一个参数都是 user_id (UUID 字符串)。
所有 SELECT/UPDATE/DELETE 必须带 user_id 过滤——SERIAL 主键 task.id 是全局的，
不带 user_id 过滤理论上可能跨用户操作（虽然 RLS 是 backstop，但代码层不能依赖它）。
"""

from datetime import timedelta
from db.database import _get, _post, _patch, _delete, now_cn

# idle 任务留存天数：超过就自动结转为 abandoned
# 2026-04-23: 从 2 改 1——避免"数据库有但前端看不见"的僵尸态（前端只看 today，
# idle 第 2 天就是这种僵尸态）。现在一过当天 idle 就转 abandoned，
# abandoned 进前端"已放弃"折叠区（2 天内可恢复）
STALE_IDLE_DAYS = 1


def _get_task_by_id(user_id: str, task_id: int) -> dict:
    """按 ID 查任务（限本人）。"""
    rows = _get("task", {
        "id": f"eq.{task_id}",
        "user_id": f"eq.{user_id}",
        "select": "*",
    })
    return rows[0] if rows else {}


def create_task(user_id: str, keyword: str, combo: str, energy_level: int,
                suggested_minutes: int | None = None,
                task_type: str = "work",
                auto_start: bool = True,
                detail: str = "") -> dict:
    """创建任务。auto_start=True 立即开始，False 则放入待完成（idle）。"""
    status = "executing" if auto_start else "idle"

    if auto_start:
        executing = get_executing_task(user_id)
        if executing:
            raise ValueError("已有执行中的任务，请先暂停、完成或放弃当前任务")

    now = now_cn().isoformat()
    started_at = now if auto_start else None

    return _post("task", {
        "user_id": user_id,
        "keyword": keyword,
        "combo": combo,
        "energy_at_start": energy_level,
        "status": status,
        "default_minutes": suggested_minutes,
        "task_type": task_type,
        "started_at": started_at,
        "created_at": now,
        "detail": detail,
    })


def pause_task(user_id: str, task_id: int) -> dict:
    """暂停任务：executing → paused。"""
    now = now_cn().isoformat()
    _patch("task", {
        "id": f"eq.{task_id}",
        "user_id": f"eq.{user_id}",
        "status": "eq.executing",
    }, {"status": "paused", "paused_at": now}, return_row=False)
    return _get_task_by_id(user_id, task_id)


def resume_task(user_id: str, task_id: int) -> dict:
    """继续任务：paused → executing。"""
    _patch("task", {
        "id": f"eq.{task_id}",
        "user_id": f"eq.{user_id}",
        "status": "eq.paused",
    }, {"status": "executing", "paused_at": None}, return_row=False)
    return _get_task_by_id(user_id, task_id)


def complete_task(user_id: str, task_id: int) -> dict:
    """完成任务：executing/paused → completed。"""
    now = now_cn().isoformat()
    _patch("task", {
        "id": f"eq.{task_id}",
        "user_id": f"eq.{user_id}",
        "status": "in.(executing,paused)",
    }, {"status": "completed", "completed_at": now}, return_row=False)
    return _get_task_by_id(user_id, task_id)


def abandon_task(user_id: str, task_id: int) -> dict:
    """放弃任务：executing/paused → abandoned。"""
    now = now_cn().isoformat()
    _patch("task", {
        "id": f"eq.{task_id}",
        "user_id": f"eq.{user_id}",
        "status": "in.(executing,paused)",
    }, {"status": "abandoned", "completed_at": now}, return_row=False)
    return _get_task_by_id(user_id, task_id)


def update_task_minutes(user_id: str, task_id: int, minutes: int) -> dict:
    """修改任务的建议时长。"""
    _patch("task", {
        "id": f"eq.{task_id}",
        "user_id": f"eq.{user_id}",
    }, {"default_minutes": minutes}, return_row=False)
    return _get_task_by_id(user_id, task_id)


def update_task_keyword(user_id: str, task_id: int, keyword: str) -> dict:
    """修改任务名。"""
    _patch("task", {
        "id": f"eq.{task_id}",
        "user_id": f"eq.{user_id}",
    }, {"keyword": keyword}, return_row=False)
    return _get_task_by_id(user_id, task_id)


def _sweep_stale_idle_tasks(user_id: str) -> None:
    """把超过 STALE_IDLE_DAYS 天前创建仍在 idle 的任务结转为 abandoned。

    静默失败——sweep 不该影响主流程，网络/DB 抖动时下次再 sweep 即可。
    """
    now = now_cn()
    cutoff = (now - timedelta(days=STALE_IDLE_DAYS)).isoformat()
    try:
        _patch("task", {
            "user_id": f"eq.{user_id}",
            "status": "eq.idle",
            "created_at": f"lt.{cutoff}",
        }, {"status": "abandoned", "completed_at": now.isoformat()}, return_row=False)
    except Exception:
        pass


def get_today_tasks(user_id: str) -> list[dict]:
    """获取今日任务视图：活跃任务（今天 created_at 且非 abandoned）
    + 最近 2 天 abandoned 任务（供前端"已放弃"折叠区 + 恢复按钮）。

    读前先 sweep 一次陈年 idle——超过 STALE_IDLE_DAYS 的 idle 自动结转 abandoned。
    """
    from db.database import ABANDONED_RETENTION_DAYS

    _sweep_stale_idle_tasks(user_id)
    now = now_cn()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    abandoned_cutoff = (now - timedelta(days=ABANDONED_RETENTION_DAYS)).isoformat()

    # 今天创建的活跃任务（含 completed、排除 abandoned）
    active = _get("task", {
        "user_id": f"eq.{user_id}",
        "created_at": f"gte.{today_start}",
        "status": "neq.abandoned",
        "select": "*",
        "order": "created_at.desc",
    })

    # 最近 2 天被放弃的任务（手动放弃 + 自动结转都在这）
    abandoned = _get("task", {
        "user_id": f"eq.{user_id}",
        "status": "eq.abandoned",
        "completed_at": f"gte.{abandoned_cutoff}",
        "select": "*",
        "order": "completed_at.desc",
    })

    return active + abandoned


def restore_task(user_id: str, task_id: int) -> dict | None:
    """把 abandoned 任务恢复成 idle，重置 created_at = now。

    不重置 created_at 会立刻又被 sweep 打回 abandoned（因为原 created_at 已超
    STALE_IDLE_DAYS）。重置相当于"用户今天想重新开始做这件事"。
    """
    task = _get_task_by_id(user_id, task_id)
    if not task or task.get("status") != "abandoned":
        return None

    now_iso = now_cn().isoformat()
    return _patch("task", {
        "id": f"eq.{task_id}",
        "user_id": f"eq.{user_id}",
    }, {
        "status": "idle",
        "created_at": now_iso,
        "completed_at": None,
    }, return_row=True)


def get_executing_task(user_id: str) -> dict | None:
    """获取当前正在执行的任务，没有则返回 None。"""
    rows = _get("task", {
        "user_id": f"eq.{user_id}",
        "status": "eq.executing",
        "select": "*",
        "order": "created_at.desc",
        "limit": "1",
    })
    return rows[0] if rows else None


def get_active_task(user_id: str) -> dict | None:
    """获取当前活跃任务（executing 或 paused），没有则返回 None。"""
    rows = _get("task", {
        "user_id": f"eq.{user_id}",
        "status": "in.(executing,paused)",
        "select": "*",
        "order": "created_at.desc",
        "limit": "1",
    })
    if not rows:
        return None
    # 优先返回 executing
    executing = [r for r in rows if r["status"] == "executing"]
    return executing[0] if executing else rows[0]


# ---- 循环任务 ----

def create_recurring_task(user_id: str, keyword: str, task_type: str = "work",
                          default_minutes: int | None = None) -> dict:
    """创建一个每日循环任务模板。"""
    return _post("recurring_task", {
        "user_id": user_id,
        "keyword": keyword,
        "task_type": task_type,
        "default_minutes": default_minutes,
    })


def get_recurring_tasks(user_id: str) -> list[dict]:
    """获取所有启用的循环任务模板。"""
    return _get("recurring_task", {
        "user_id": f"eq.{user_id}",
        "active": "eq.1",
        "select": "*",
        "order": "created_at.asc",
    })


def delete_recurring_task(user_id: str, rec_id: int) -> None:
    """停用循环任务（软删除）。"""
    _patch("recurring_task", {
        "id": f"eq.{rec_id}",
        "user_id": f"eq.{user_id}",
    }, {"active": 0}, return_row=False)


def spawn_daily_tasks(user_id: str) -> None:
    """每天首次调用时，为该用户所有启用的循环任务生成今日 idle 任务。"""
    today_start = now_cn().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    now = now_cn().isoformat()

    recurring = _get("recurring_task", {
        "user_id": f"eq.{user_id}",
        "active": "eq.1",
        "select": "*",
    })

    for rec in recurring:
        # 检查今天是否已有该循环任务
        existing = _get("task", {
            "user_id": f"eq.{user_id}",
            "keyword": f"eq.{rec['keyword']}",
            "created_at": f"gte.{today_start}",
            "combo": "eq.recurring",
            "status": "in.(idle,executing,paused,completed)",
            "select": "id",
            "limit": "1",
        })
        if not existing:
            _post("task", {
                "user_id": user_id,
                "keyword": rec["keyword"],
                "combo": "recurring",
                "energy_at_start": None,
                "status": "idle",
                "default_minutes": rec["default_minutes"],
                "task_type": rec["task_type"],
                "created_at": now,
            }, return_row=False)


def start_task(user_id: str, task_id: int, energy_level: int,
               allowed_from: tuple = ("idle", "scheduled")) -> dict:
    """启动一个任务：idle / scheduled → executing。

    任务不存在 / 状态不在 allowed_from / 已有执行中任务 → ValueError。
    """
    executing = get_executing_task(user_id)
    if executing:
        raise ValueError("已有执行中的任务，请先暂停、完成或放弃当前任务")

    task = _get_task_by_id(user_id, task_id)
    if not task:
        raise ValueError("任务不存在")
    if task["status"] not in allowed_from:
        raise ValueError(f"任务状态为 {task['status']}，无法启动")

    now = now_cn().isoformat()
    _patch("task", {
        "id": f"eq.{task_id}",
        "user_id": f"eq.{user_id}",
    }, {"status": "executing", "energy_at_start": energy_level, "started_at": now},
       return_row=False)
    return _get_task_by_id(user_id, task_id)


def create_scheduled_task(user_id: str, keyword: str, scheduled_at: str, combo: str,
                          energy_level: int | None = None,
                          suggested_minutes: int | None = None,
                          task_type: str = "work") -> dict:
    """创建一个预定任务。"""
    now = now_cn().isoformat()
    return _post("task", {
        "user_id": user_id,
        "keyword": keyword,
        "combo": combo,
        "energy_at_start": energy_level,
        "status": "scheduled",
        "default_minutes": suggested_minutes,
        "task_type": task_type,
        "scheduled_at": scheduled_at,
        "created_at": now,
    })


def get_scheduled_tasks(user_id: str) -> list[dict]:
    """获取所有预定任务，按预定时间排序。"""
    return _get("task", {
        "user_id": f"eq.{user_id}",
        "status": "eq.scheduled",
        "select": "*",
        "order": "scheduled_at.asc",
    })


def get_due_scheduled_tasks(user_id: str) -> list[dict]:
    """获取已到期的预定任务。"""
    now = now_cn().isoformat()
    return _get("task", {
        "user_id": f"eq.{user_id}",
        "status": "eq.scheduled",
        "scheduled_at": f"lte.{now}",
        "select": "*",
    })


def delete_task(user_id: str, task_id: int) -> None:
    """从数据库中彻底删除一个任务（限本人）。"""
    _delete("task", {
        "id": f"eq.{task_id}",
        "user_id": f"eq.{user_id}",
    })
