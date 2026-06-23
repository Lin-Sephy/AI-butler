"""任务管理：单任务闭环（创建 → 执行 → 暂停 → 完成/放弃）。

v2 多用户改造（2026-04-15）：所有公开函数第一个参数都是 user_id (UUID 字符串)。
所有 SELECT/UPDATE/DELETE 必须带 user_id 过滤——SERIAL 主键 task.id 是全局的，
不带 user_id 过滤理论上可能跨用户操作（虽然 RLS 是 backstop，但代码层不能依赖它）。
"""

from datetime import datetime, timedelta
from db.database import _get, _post, _patch, _delete, now_cn

TASK_DAY_START_HOUR = 4
MAX_OPEN_FOCUS_MINUTES = 8 * 60


def _task_day_start(now=None):
    """返回当前任务日的起点。任务日按北京时间 04:00 刷新。"""
    now = now or now_cn()
    start = now.replace(hour=TASK_DAY_START_HOUR, minute=0, second=0, microsecond=0)
    if now < start:
        start -= timedelta(days=1)
    return start


def _task_day_window(now=None):
    start = _task_day_start(now)
    return start, start + timedelta(days=1)


def _get_task_by_id(user_id: str, task_id: int) -> dict:
    """按 ID 查任务（限本人）。"""
    rows = _get("task", {
        "id": f"eq.{task_id}",
        "user_id": f"eq.{user_id}",
        "select": "*",
    })
    return rows[0] if rows else {}


def create_task(user_id: str, keyword: str, combo: str, energy_level: int | None = None,
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


def resume_task(user_id: str, task_id: int, pause_started_at: str | None = None,
                resumed_at: str | None = None,
                paused_ms: int | None = None,
                base_started_at: str | None = None) -> dict:
    """继续任务：paused → executing。

    前端专注遮罩会先本地暂停，再后台同步。resume 可携带本地暂停区间；
    如果 pause 请求曾失败，后端也能在 resume 时扣掉这段暂停时间。
    """
    task = _get_task_by_id(user_id, task_id)
    if not task or task.get("status") not in ("paused", "executing"):
        return task

    updates = {"status": "executing", "paused_at": None}
    started = _parse_task_datetime(task.get("started_at"))
    delta = _client_pause_delta(
        task,
        pause_started_at=pause_started_at,
        resumed_at=resumed_at,
        paused_ms=paused_ms,
        base_started_at=base_started_at,
    )

    if delta is None and task.get("status") == "paused":
        paused_at = _parse_task_datetime(task.get("paused_at"))
        now = now_cn()
        if started and paused_at and now > paused_at:
            delta = now - paused_at

    if started and delta and delta.total_seconds() > 0:
        updates["started_at"] = (started + delta).isoformat()

    _patch("task", {
        "id": f"eq.{task_id}",
        "user_id": f"eq.{user_id}",
    }, updates, return_row=False)
    return _get_task_by_id(user_id, task_id)


def complete_task(user_id: str, task_id: int, pause_started_at: str | None = None,
                  resumed_at: str | None = None,
                  paused_ms: int | None = None,
                  base_started_at: str | None = None) -> dict:
    """完成任务：executing/paused → completed。用实际用时覆盖 default_minutes。"""
    now = now_cn()
    task = _get_task_by_id(user_id, task_id)
    updates = {"status": "completed", "completed_at": now.isoformat()}
    started = task.get("started_at")
    if started:
        try:
            dt = _parse_task_datetime(started)
            if dt is None:
                raise ValueError("invalid started_at")
            delta = _client_pause_delta(
                task,
                pause_started_at=pause_started_at,
                resumed_at=resumed_at,
                paused_ms=paused_ms,
                base_started_at=base_started_at,
            )
            if delta and delta.total_seconds() > 0:
                dt = dt + delta
                updates["started_at"] = dt.isoformat()
            end_dt = now
            if task.get("status") == "paused":
                paused_at = _parse_task_datetime(task.get("paused_at"))
                if paused_at and not delta:
                    end_dt = paused_at
            cap = int(task.get("default_minutes") or MAX_OPEN_FOCUS_MINUTES)
            actual = max(1, min(cap, round((end_dt - dt).total_seconds() / 60)))
            updates["default_minutes"] = actual
        except (ValueError, TypeError):
            pass
    _patch("task", {
        "id": f"eq.{task_id}",
        "user_id": f"eq.{user_id}",
        "status": "in.(executing,paused)",
    }, updates, return_row=False)
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


def _sweep_expired_scheduled_tasks(user_id: str) -> None:
    """把所属任务日已经结束的未开始预定任务结转为 abandoned。

    静默失败——sweep 不该影响主流程，网络/DB 抖动时下次再 sweep 即可。
    """
    now = now_cn()
    today_start = _task_day_start(now).isoformat()
    try:
        _patch("task", {
            "user_id": f"eq.{user_id}",
            "status": "in.(idle,scheduled)",
            "scheduled_at": f"lt.{today_start}",
        }, {"status": "abandoned", "completed_at": now.isoformat()}, return_row=False)
    except Exception:
        pass


def _parse_task_datetime(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _same_task_instant(left: str | None, right: str | None) -> bool:
    left_dt = _parse_task_datetime(left)
    right_dt = _parse_task_datetime(right)
    return bool(left_dt and right_dt and left_dt == right_dt)


def _client_pause_delta(task: dict, pause_started_at: str | None = None,
                        resumed_at: str | None = None,
                        paused_ms: int | None = None,
                        base_started_at: str | None = None) -> timedelta | None:
    """Return a client-reported pause delta, guarded against double-apply."""
    if base_started_at and not _same_task_instant(task.get("started_at"), base_started_at):
        return None

    start = _parse_task_datetime(pause_started_at)
    end = _parse_task_datetime(resumed_at)
    if start and end and end > start:
        return end - start

    try:
        ms = int(paused_ms) if paused_ms is not None else 0
    except (TypeError, ValueError):
        ms = 0
    if ms > 0:
        return timedelta(milliseconds=ms)
    return None


def _sweep_finished_focus_tasks(user_id: str) -> None:
    """把已到终点但仍 executing 的任务结算为 completed。

    - 倒计时 focus：按 default_minutes 到点结算。
    - 正计时 open：没有 default_minutes，按 MAX_OPEN_FOCUS_MINUTES 封顶结算。
    """
    now = now_cn()
    try:
        rows = _get("task", {
            "user_id": f"eq.{user_id}",
            "status": "eq.executing",
            "started_at": "not.is.null",
            "select": "id,started_at,default_minutes",
        })
    except Exception:
        return

    for task in rows:
        started = _parse_task_datetime(task.get("started_at"))
        minutes = task.get("default_minutes") or MAX_OPEN_FOCUS_MINUTES
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            continue
        if not started or minutes <= 0:
            continue
        if now >= started + timedelta(minutes=minutes):
            try:
                _patch("task", {
                    "id": f"eq.{task['id']}",
                    "user_id": f"eq.{user_id}",
                    "status": "eq.executing",
                }, {"status": "completed", "completed_at": (started + timedelta(minutes=minutes)).isoformat()},
                    return_row=False)
            except Exception:
                pass


def get_today_tasks(user_id: str) -> list[dict]:
    """获取今日任务视图：活跃任务（今天 created_at 且非 abandoned）
    + 所有未完成的普通待办（无 scheduled_at 的 idle）
    + 跨天仍在执行/暂停的任务
    + 最近 2 天 abandoned 任务（供前端"已放弃"折叠区 + 恢复按钮）。

    读前先 sweep 一次过期预定任务；普通 idle 不再自动结转。
    """
    from db.database import ABANDONED_RETENTION_DAYS

    _sweep_expired_scheduled_tasks(user_id)
    _sweep_finished_focus_tasks(user_id)
    now = now_cn()
    today_start_dt, today_end_dt = _task_day_window(now)
    today_start = today_start_dt.isoformat()
    abandoned_cutoff = (now - timedelta(days=ABANDONED_RETENTION_DAYS)).isoformat()

    today_end = today_end_dt.isoformat()

    # 今天创建的活跃任务（含 completed、排除 abandoned）
    active = _get("task", {
        "user_id": f"eq.{user_id}",
        "created_at": f"gte.{today_start}",
        "status": "neq.abandoned",
        "select": "*",
        "order": "created_at.desc",
    })

    # scheduled_at 在今天的任务（不管哪天创建的，比如昨天建的"明天9点"）
    scheduled_today = _get("task", [
        ("user_id", f"eq.{user_id}"),
        ("scheduled_at", f"gte.{today_start}"),
        ("scheduled_at", f"lt.{today_end}"),
        ("status", "neq.abandoned"),
        ("select", "*"),
    ])

    # 合并去重（同一个任务可能两个查询都命中）
    seen = {t["id"] for t in active}
    for t in scheduled_today:
        if t["id"] not in seen:
            active.append(t)
            seen.add(t["id"])

    # 普通待办没有过期语义：昨天没做完，今天仍然应该留在任务页。
    unscheduled_idle = _get("task", {
        "user_id": f"eq.{user_id}",
        "scheduled_at": "is.null",
        "status": "eq.idle",
        "select": "*",
        "order": "created_at.desc",
    })
    for t in unscheduled_idle:
        if t["id"] not in seen:
            active.append(t)
            seen.add(t["id"])

    # 跨天仍在执行/暂停的任务也必须出现在任务页。
    # 否则后端 start_task 会因为已有 executing 拦截，前端却看不到那条任务，用户无法处理。
    carried_active = _get("task", {
        "user_id": f"eq.{user_id}",
        "status": "in.(executing,paused)",
        "select": "*",
        "order": "created_at.desc",
    })
    for t in carried_active:
        if t["id"] not in seen:
            active.append(t)
            seen.add(t["id"])

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

    恢复后清掉 scheduled_at，避免过期预定任务刚恢复又被 sweep 打回 abandoned。
    这相当于"用户今天想重新开始做这件事"。
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
        "scheduled_at": None,
        "completed_at": None,
    }, return_row=True)


def get_executing_task(user_id: str) -> dict | None:
    """获取当前正在执行的任务，没有则返回 None。"""
    _sweep_finished_focus_tasks(user_id)
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
    _sweep_finished_focus_tasks(user_id)
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
                          default_minutes: int | None = None,
                          scheduled_time: str | None = None) -> dict:
    """创建一个每日循环任务模板。同名模板已存在则更新，不重复建。"""
    existing = _get("recurring_task", {
        "user_id": f"eq.{user_id}",
        "keyword": f"eq.{keyword}",
        "active": "eq.1",
        "select": "*",
        "limit": "1",
    })
    if existing:
        update = {}
        if default_minutes is not None:
            update["default_minutes"] = default_minutes
        if scheduled_time is not None:
            update["scheduled_time"] = scheduled_time
        if update:
            _patch("recurring_task", {
                "id": f"eq.{existing[0]['id']}",
                "user_id": f"eq.{user_id}",
            }, update, return_row=False)
        return {**existing[0], **update}

    data = {
        "user_id": user_id,
        "keyword": keyword,
        "task_type": task_type,
        "default_minutes": default_minutes,
    }
    if scheduled_time:
        data["scheduled_time"] = scheduled_time
    return _post("recurring_task", data)


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


import threading
_spawn_locks: dict[str, threading.Lock] = {}
_spawn_locks_guard = threading.Lock()

def spawn_daily_tasks(user_id: str) -> None:
    """每天首次调用时，为该用户所有启用的循环任务生成今日 idle 任务。"""
    with _spawn_locks_guard:
        if user_id not in _spawn_locks:
            _spawn_locks[user_id] = threading.Lock()
        lock = _spawn_locks[user_id]

    if not lock.acquire(blocking=False):
        return

    try:
        _spawn_daily_tasks_impl(user_id)
    finally:
        lock.release()


def _spawn_daily_tasks_impl(user_id: str) -> None:
    now_dt = now_cn()
    today_start_dt, today_end_dt = _task_day_window(now_dt)
    today_start = today_start_dt.isoformat()
    today_end = today_end_dt.isoformat()
    now = now_dt.isoformat()

    recurring = _get("recurring_task", {
        "user_id": f"eq.{user_id}",
        "active": "eq.1",
        "select": "*",
    })

    today_date = now_dt.strftime("%Y-%m-%d")

    for rec in recurring:
        # 检查今天是否已有该循环任务
        existing = _get("task", [
            ("user_id", f"eq.{user_id}"),
            ("keyword", f"eq.{rec['keyword']}"),
            ("created_at", f"gte.{today_start}"),
            ("created_at", f"lt.{today_end}"),
            ("combo", "eq.recurring"),
            ("status", "in.(idle,executing,paused,completed,abandoned,scheduled)"),
            ("select", "id"),
            ("limit", "1"),
        ])
        if not existing:
            stime = rec.get("scheduled_time")
            if stime:
                now_time = now_dt.strftime("%H:%M")
                if stime > now_time:
                    scheduled_at = f"{today_date}T{stime}:00"
                else:
                    tomorrow = (now_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                    scheduled_at = f"{tomorrow}T{stime}:00"
                status = "scheduled"
            else:
                scheduled_at = None
                status = "idle"

            _post("task", {
                "user_id": user_id,
                "keyword": rec["keyword"],
                "combo": "recurring",
                "energy_at_start": None,
                "status": status,
                "scheduled_at": scheduled_at,
                "default_minutes": rec["default_minutes"],
                "task_type": rec["task_type"],
                "created_at": now,
            }, return_row=False)


def start_task(user_id: str, task_id: int, energy_level: int | None = None,
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
