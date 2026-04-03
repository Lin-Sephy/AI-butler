"""任务管理：单任务闭环（创建 → 执行 → 暂停 → 完成/放弃）。"""

from db.database import get_connection, now_cn


def create_task(keyword: str, combo: str, energy_level: int,
                suggested_minutes: int | None = None,
                task_type: str = "work",
                auto_start: bool = True) -> dict:
    """创建任务。auto_start=True 立即开始，False 则放入待完成（idle）。"""
    status = "executing" if auto_start else "idle"

    if auto_start:
        executing = get_executing_task()
        if executing:
            raise ValueError("已有执行中的任务，请先暂停、完成或放弃当前任务")

    conn = get_connection()
    now = now_cn().isoformat()
    started_at = now if auto_start else None

    cursor = conn.execute(
        "INSERT INTO task (keyword, combo, energy_at_start, status, default_minutes, task_type, started_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (keyword, combo, energy_level, status, suggested_minutes, task_type, started_at, now),
    )
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "id": task_id,
        "keyword": keyword,
        "combo": combo,
        "energy_at_start": energy_level,
        "status": status,
        "default_minutes": suggested_minutes,
        "task_type": task_type,
        "started_at": started_at,
    }


def pause_task(task_id: int) -> dict:
    """暂停任务：executing → paused。"""
    conn = get_connection()
    now = now_cn().isoformat()
    conn.execute(
        "UPDATE task SET status = 'paused', paused_at = ? WHERE id = ? AND status = 'executing'",
        (now, task_id),
    )
    conn.commit()
    task = _get_task_by_id(conn, task_id)
    conn.close()
    return task


def resume_task(task_id: int) -> dict:
    """继续任务：paused → executing。"""
    conn = get_connection()
    conn.execute(
        "UPDATE task SET status = 'executing', paused_at = NULL WHERE id = ? AND status = 'paused'",
        (task_id,),
    )
    conn.commit()
    task = _get_task_by_id(conn, task_id)
    conn.close()
    return task


def complete_task(task_id: int) -> dict:
    """完成任务：executing/paused → completed。"""
    conn = get_connection()
    now = now_cn().isoformat()
    conn.execute(
        "UPDATE task SET status = 'completed', completed_at = ? WHERE id = ? AND status IN ('executing', 'paused')",
        (now, task_id),
    )
    conn.commit()
    task = _get_task_by_id(conn, task_id)
    conn.close()
    return task


def abandon_task(task_id: int) -> dict:
    """放弃任务：executing/paused → abandoned。"""
    conn = get_connection()
    now = now_cn().isoformat()
    conn.execute(
        "UPDATE task SET status = 'abandoned', completed_at = ? WHERE id = ? AND status IN ('executing', 'paused')",
        (now, task_id),
    )
    conn.commit()
    task = _get_task_by_id(conn, task_id)
    conn.close()
    return task


def update_task_minutes(task_id: int, minutes: int) -> dict:
    """修改任务的建议时长。"""
    conn = get_connection()
    conn.execute(
        "UPDATE task SET default_minutes = ? WHERE id = ?",
        (minutes, task_id),
    )
    conn.commit()
    task = _get_task_by_id(conn, task_id)
    conn.close()
    return task


def get_today_tasks() -> list[dict]:
    """获取今天的所有任务（不含已放弃），按创建时间倒序。"""
    conn = get_connection()
    today_start = now_cn().replace(hour=0, minute=0, second=0).isoformat()
    rows = conn.execute(
        "SELECT * FROM task WHERE created_at >= ? AND status != 'abandoned' ORDER BY created_at DESC",
        (today_start,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_executing_task() -> dict | None:
    """获取当前正在执行的任务，没有则返回 None。"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM task WHERE status = 'executing' ORDER BY created_at DESC LIMIT 1",
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_active_task() -> dict | None:
    """获取当前活跃任务（优先 executing，其次最近的 paused），没有则返回 None。"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM task WHERE status IN ('executing', 'paused') "
        "ORDER BY CASE status WHEN 'executing' THEN 0 ELSE 1 END, created_at DESC LIMIT 1",
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ---- 循环任务 ----

def create_recurring_task(keyword: str, task_type: str = "work",
                          default_minutes: int | None = None) -> dict:
    """创建一个每日循环任务模板。"""
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO recurring_task (keyword, task_type, default_minutes) VALUES (?, ?, ?)",
        (keyword, task_type, default_minutes),
    )
    rec_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": rec_id, "keyword": keyword, "task_type": task_type,
            "default_minutes": default_minutes, "active": 1}


def get_recurring_tasks() -> list[dict]:
    """获取所有启用的循环任务模板。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM recurring_task WHERE active = 1 ORDER BY created_at",
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_recurring_task(rec_id: int) -> None:
    """停用循环任务（软删除）。"""
    conn = get_connection()
    conn.execute("UPDATE recurring_task SET active = 0 WHERE id = ?", (rec_id,))
    conn.commit()
    conn.close()


def spawn_daily_tasks() -> None:
    """每天首次调用时，为所有启用的循环任务生成今日 idle 任务。"""
    conn = get_connection()
    today_start = now_cn().replace(hour=0, minute=0, second=0).isoformat()
    now = now_cn().isoformat()

    recurring = conn.execute(
        "SELECT * FROM recurring_task WHERE active = 1",
    ).fetchall()

    for rec in recurring:
        # 检查今天是否已有该循环任务（任何状态，含已完成）
        existing = conn.execute(
            "SELECT id FROM task WHERE keyword = ? AND created_at >= ? AND combo = 'recurring' "
            "AND status IN ('idle', 'executing', 'paused', 'completed')",
            (rec["keyword"], today_start),
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO task (keyword, combo, energy_at_start, status, default_minutes, task_type, created_at) "
                "VALUES (?, 'recurring', NULL, 'idle', ?, ?, ?)",
                (rec["keyword"], rec["default_minutes"], rec["task_type"], now),
            )

    conn.commit()
    conn.close()


def start_idle_task(task_id: int, energy_level: int) -> dict:
    """启动一个 idle 状态的任务（用于循环任务点击开始）。"""
    executing = get_executing_task()
    if executing:
        raise ValueError("已有执行中的任务，请先暂停、完成或放弃当前任务")

    conn = get_connection()
    now = now_cn().isoformat()
    conn.execute(
        "UPDATE task SET status = 'executing', energy_at_start = ?, started_at = ? "
        "WHERE id = ? AND status = 'idle'",
        (energy_level, now, task_id),
    )
    conn.commit()
    task = _get_task_by_id(conn, task_id)
    conn.close()
    return task


def create_scheduled_task(keyword: str, scheduled_at: str, combo: str,
                          energy_level: int | None = None,
                          suggested_minutes: int | None = None,
                          task_type: str = "work") -> dict:
    """创建一个预定任务（scheduled 状态，不立即执行）。"""
    conn = get_connection()
    now = now_cn().isoformat()
    cursor = conn.execute(
        "INSERT INTO task (keyword, combo, energy_at_start, status, default_minutes, "
        "task_type, scheduled_at, created_at) VALUES (?, ?, ?, 'scheduled', ?, ?, ?, ?)",
        (keyword, combo, energy_level, suggested_minutes, task_type, scheduled_at, now),
    )
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {
        "id": task_id, "keyword": keyword, "combo": combo,
        "status": "scheduled", "default_minutes": suggested_minutes,
        "task_type": task_type, "scheduled_at": scheduled_at,
    }


def get_scheduled_tasks() -> list[dict]:
    """获取所有预定任务（scheduled 状态），按预定时间排序。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM task WHERE status = 'scheduled' ORDER BY scheduled_at",
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_due_scheduled_tasks() -> list[dict]:
    """获取已到期的预定任务（scheduled_at <= 当前时间）。"""
    conn = get_connection()
    now = now_cn().isoformat()
    rows = conn.execute(
        "SELECT * FROM task WHERE status = 'scheduled' AND scheduled_at <= ?",
        (now,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def start_scheduled_task(task_id: int, energy_level: int) -> dict:
    """启动一个预定任务：scheduled → executing。"""
    executing = get_executing_task()
    if executing:
        raise ValueError("已有执行中的任务，请先暂停、完成或放弃当前任务")

    conn = get_connection()
    now = now_cn().isoformat()
    conn.execute(
        "UPDATE task SET status = 'executing', energy_at_start = ?, started_at = ? "
        "WHERE id = ? AND status = 'scheduled'",
        (energy_level, now, task_id),
    )
    conn.commit()
    task = _get_task_by_id(conn, task_id)
    conn.close()
    return task


def delete_task(task_id: int) -> None:
    """从数据库中彻底删除一个任务。"""
    conn = get_connection()
    conn.execute("DELETE FROM task WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()


def _get_task_by_id(conn, task_id: int) -> dict:
    """内部工具：按 ID 查任务。"""
    row = conn.execute("SELECT * FROM task WHERE id = ?", (task_id,)).fetchone()
    if row:
        return dict(row)
    return {}
