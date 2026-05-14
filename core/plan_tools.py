"""计划模式的 function calling 工具：给 DS 按需查数据。

v5.0 架构（见开工文档）：
- 计划模式下 DS 通过 DeepSeek function calling 按需调用查询工具
- 闲聊模式不注册工具（DS 不知道这些数据存在）
- 所有工具都是只读查询；写入走独立的结构化提取流程
- Step 0 实测通过（召回率 100%，参数合法率 100%）
"""
import json
import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from db.database import (
    get_tasks_recent,
    get_daily_routine,
    now_cn,
)
from core.task_manager import (
    delete_task as _delete_task_impl,
    _get_task_by_id,
    get_today_tasks,
    create_task as _create_task_impl,
    create_scheduled_task as _create_scheduled_task_impl,
    create_recurring_task as _create_recurring_impl,
    spawn_daily_tasks,
)


def _parse_scheduled_at(raw) -> str | None:
    """把 DS 传的 scheduled_at 解析成 ISO 字符串。

    接受：
      - 完整 ISO 8601（含/不含秒、含/不含时区）
      - 'YYYY-MM-DD HH:MM[:SS]'（'/' 分隔也行）
      - 'HH:MM'（按今天补日期）
    解析失败返 None，调用方报错让 DS 改。
    """
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None

    # 纯 HH:MM → 今天
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if m:
        h, mm = int(m.group(1)), int(m.group(2))
        if 0 <= h < 24 and 0 <= mm < 60:
            today = now_cn().strftime("%Y-%m-%d")
            return f"{today}T{h:02d}:{mm:02d}:00"
        return None

    # 常见变体归一化成 ISO
    normalized = s.replace("/", "-").replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return dt.isoformat()


# ════════════════════════════════════════════════════════════
# 工具 Schema（传给 DeepSeek）
# ════════════════════════════════════════════════════════════

PLAN_MODE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_tasks",
            "description": (
                "查铲屎官当前任务栏的所有任务（和任务栏显示完全一致）。"
                "包含今天的 idle / executing / paused / scheduled / completed 任务，"
                "以及最近 2 天的 abandoned 任务（可恢复）。看不到更早的历史。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_stats",
            "description": "查用户的专注统计（最常专注的时段、平均时长、完成率）",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_schedule",
            "description": "查今天的日程（具体事件和日常作息）",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_tasks",
            "description": (
                "批量删除任务栏里的多条任务。一次传一个 task_id 列表，比反复调 delete_task 高效。"
                "用户表示要取消这些任务时可调用。别主动删用户自建、对话里没讨论过的任务。"
                "列表里的 task_id 必须从 query_tasks 返回值里取。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "要删除的任务 id 列表（来自 query_tasks 返回的 task_id）",
                    },
                },
                "required": ["task_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_task",
            "description": (
                "删除单条任务。多条时优先用 delete_tasks 批量。"
                "用户表示要取消该任务时可调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "要删除的任务 id（来自 query_tasks 返回的 task_id）",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_tasks",
            "description": (
                "批量创建任务，一次写入任务栏。用户和你讨论完计划、表示要记下来时调用。"
                "一次传一个 tasks 数组，包含多条任务；不要一条一条调。"
                "不传 scheduled_at 的任务以 idle（待完成）状态写入、不自动开始；"
                "传了 scheduled_at 的任务变成 scheduled（预定）状态，到期会提醒用户。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "description": "要创建的任务列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "keyword": {
                                    "type": "string",
                                    "description": "任务名（用户原话，简短具体）",
                                },
                                "minutes": {
                                    "type": "integer",
                                    "description": "建议时长（分钟），不确定填 null",
                                },
                                "scheduled_at": {
                                    "type": "string",
                                    "description": (
                                        "用户指定了时间（如'明天早上 9 点'、'周五 14:00'）时填。"
                                        "格式用 'YYYY-MM-DD HH:MM'（推荐，用 user message 里的当前时间推算）。"
                                        "只填 'HH:MM' 会按今天算。没指定时间就别填。"
                                    ),
                                },
                                "recurring": {
                                    "type": "boolean",
                                    "description": (
                                        "用户说'每天都要做'、'每日'、'循环'时设为 true。"
                                        "每日循环任务每天自动出现在任务栏。默认 false。"
                                        "可同时填 scheduled_at 指定每天几点（如 recurring=true + scheduled_at='09:00'）。"
                                    ),
                                },
                            },
                            "required": ["keyword"],
                        },
                    },
                },
                "required": ["tasks"],
            },
        },
    },
]


# ════════════════════════════════════════════════════════════
# 工具实现
# ════════════════════════════════════════════════════════════


def _tool_query_tasks(user_id: str, args: dict) -> dict:
    tasks = get_today_tasks(user_id)
    records = [
        {
            "task_id": t.get("id"),
            "keyword": t.get("keyword"),
            "status": t.get("status"),
            "created_at": t.get("created_at"),
            "started_at": t.get("started_at"),
            "completed_at": t.get("completed_at"),
            "scheduled_at": t.get("scheduled_at"),
            "minutes": t.get("default_minutes"),
            "combo": t.get("combo"),
        }
        for t in tasks
    ]
    return {"count": len(records), "records": records}


def _tool_query_stats(user_id: str, args: dict) -> dict:
    """从最近 30 天任务记录算统计。纯 Python 聚合，无 LLM。"""
    tasks = get_tasks_recent(user_id, days=30)
    if not tasks:
        return {"message": "最近 30 天还没有任务记录"}

    # 完成率 = 完成数 / 真尝试过的任务数（completed + abandoned）
    # 分母不包括 idle / scheduled 等未动过的任务，避免把"还没开始"的也当成"没完成"
    total = len(tasks)
    completed = sum(1 for t in tasks if t.get("status") == "completed")
    abandoned = sum(1 for t in tasks if t.get("status") == "abandoned")
    attempted = completed + abandoned
    completion_rate = round(completed / attempted * 100, 1) if attempted else 0

    # 平均专注时长（只算完成的任务的 default_minutes）
    durations = [
        t["default_minutes"]
        for t in tasks
        if t.get("status") == "completed" and t.get("default_minutes")
    ]
    avg_minutes = round(sum(durations) / len(durations), 1) if durations else None

    # 最常专注时段：和数据页 hours_24 保持一致，按北京时间 started_at 分桶并累计完成分钟数。
    hours = [0] * 24
    for t in tasks:
        if t.get("status") != "completed":
            continue
        started = t.get("started_at")
        if started:
            dt = _to_cn_datetime(started)
            if dt:
                hours[dt.hour] += (t.get("default_minutes") or 0)
    top_hours = sorted(
        [(h, minutes) for h, minutes in enumerate(hours) if minutes > 0],
        key=lambda item: item[1],
        reverse=True,
    )[:3]
    top_hours_desc = [
        f"{h:02d}:00-{(h + 1) % 24:02d}:00 ({minutes}分钟)"
        for h, minutes in top_hours
    ]

    # 最常做的事
    keyword_counter: Counter = Counter(t["keyword"] for t in tasks if t.get("keyword"))
    top_keywords = [f"{k} ({n}次)" for k, n in keyword_counter.most_common(5)]

    return {
        "最近30天任务总数": total,
        "完成数": completed,
        "放弃数": abandoned,
        "完成率": f"{completion_rate}%",
        "平均专注时长": f"{avg_minutes} 分钟" if avg_minutes else "暂无",
        "最常专注时段": top_hours_desc or ["数据不足"],
        "最常做的事": top_keywords or ["暂无"],
    }


def _to_cn_datetime(iso: str):
    """ISO 时间字符串转北京时间。Supabase 可能返回 UTC Z，统计口径要和数据页一致。"""
    CN_TZ = timezone(timedelta(hours=8))
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=CN_TZ)
    return dt.astimezone(CN_TZ)


def _tool_query_schedule(user_id: str, args: dict) -> dict:
    """今日事件（scheduled_at 在今天的任务）+ 用户日常作息。"""
    today = now_cn().strftime("%Y-%m-%d")

    tasks = get_tasks_recent(user_id, days=3)
    today_events = []
    for t in tasks:
        scheduled = t.get("scheduled_at") or ""
        if scheduled.startswith(today):
            today_events.append({
                "time": scheduled,
                "keyword": t.get("keyword"),
            })

    routine = get_daily_routine(user_id)

    return {
        "today": today,
        "今日事件": today_events or "（今天没有特别事件）",
        "日常作息": routine or "（铲屎官还没设置日常作息）",
    }


def _tool_delete_task(user_id: str, args: dict) -> dict:
    """不真删，返回待删任务详情，由前端弹窗让用户确认后再删。"""
    task_id = args.get("task_id")
    try:
        task_id = int(task_id)
    except (TypeError, ValueError):
        return {"error": "task_id 必须是整数"}

    task = _get_task_by_id(user_id, task_id)
    if not task:
        return {"error": f"task_id={task_id} 不存在"}

    return {
        "ok": True,
        "pending_deletes": [{
            "task_id": task.get("id"),
            "keyword": task.get("keyword"),
            "status": task.get("status"),
            "minutes": task.get("default_minutes"),
            "combo": task.get("combo"),
        }],
        "message": "已提交删除确认，等铲屎官在弹窗里确认后才会真正删除。",
    }


def _tool_delete_tasks(user_id: str, args: dict) -> dict:
    """不真删，返回待删任务详情列表，由前端弹窗让用户确认后再删。"""
    raw = args.get("task_ids")
    if not isinstance(raw, list) or not raw:
        return {"error": "task_ids 必须是非空整数列表"}

    pending: list[dict] = []
    failed: list[dict] = []
    for item in raw:
        try:
            tid = int(item)
        except (TypeError, ValueError):
            failed.append({"task_id": item, "reason": "不是整数"})
            continue

        task = _get_task_by_id(user_id, tid)
        if not task:
            failed.append({"task_id": tid, "reason": "不存在"})
            continue

        pending.append({
            "task_id": task.get("id"),
            "keyword": task.get("keyword"),
            "status": task.get("status"),
            "minutes": task.get("default_minutes"),
            "combo": task.get("combo"),
        })

    result: dict = {
        "ok": True,
        "pending_deletes": pending,
        "message": f"已提交 {len(pending)} 条删除确认，等铲屎官在弹窗里确认后才会真正删除。",
    }
    if failed:
        result["failed"] = failed
    return result


def _tool_create_tasks(user_id: str, args: dict) -> dict:
    """批量创建任务（一次多条，省轮数）。

    - 无 scheduled_at：写成 idle（待完成），不自动开始
    - 有 scheduled_at：写成 scheduled（预定），到期提醒
    """
    raw = args.get("tasks")
    if not isinstance(raw, list) or not raw:
        return {"error": "tasks 必须是非空任务列表"}

    # v5.0 不再依赖精力档位，task.energy_at_start 写 NULL（DB 允许）
    energy_level = None

    created: list[dict] = []
    failed: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            failed.append({"task": item, "reason": "不是对象"})
            continue
        keyword = (item.get("keyword") or "").strip()
        if not keyword:
            failed.append({"task": item, "reason": "缺 keyword"})
            continue

        minutes = item.get("minutes")
        if minutes is not None:
            try:
                minutes = max(1, min(480, int(minutes)))
            except (TypeError, ValueError):
                minutes = None

        scheduled_raw = item.get("scheduled_at")
        scheduled_iso = _parse_scheduled_at(scheduled_raw) if scheduled_raw else None
        if scheduled_raw and not scheduled_iso:
            failed.append({
                "keyword": keyword,
                "reason": f"scheduled_at 格式不对：{scheduled_raw!r}（请用 'YYYY-MM-DD HH:MM'）",
            })
            continue

        is_recurring = bool(item.get("recurring"))

        # 同时间冲突检测：有 scheduled_at 时查今天同时间是否已有任务
        if scheduled_iso:
            hhmm = scheduled_iso[11:16]
            today_tasks = get_today_tasks(user_id)
            conflicts = [
                t for t in today_tasks
                if t.get("scheduled_at") and t["scheduled_at"][11:16] == hhmm
                and t.get("status") not in ("completed", "abandoned")
            ]
            if conflicts:
                conflict_info = [{"task_id": t["id"], "keyword": t["keyword"], "time": hhmm} for t in conflicts]
                failed.append({
                    "keyword": keyword,
                    "reason": f"{hhmm} 已有任务：{', '.join(t['keyword'] for t in conflicts)}。请问铲屎官是要调整时间，还是在同一时间再加一个？",
                    "conflicts": conflict_info,
                })
                continue

        try:
            if is_recurring:
                stime = None
                if scheduled_iso:
                    m = scheduled_iso[11:16]  # "HH:MM"
                    if m:
                        stime = m
                rec = _create_recurring_impl(user_id, keyword, default_minutes=minutes, scheduled_time=stime)
                spawn_daily_tasks(user_id)
                created.append({
                    "task_id": rec.get("id"),
                    "keyword": keyword,
                    "minutes": minutes,
                    "recurring": True,
                    "scheduled_time": stime,
                    "status": "recurring",
                })
            elif scheduled_iso:
                row = _create_scheduled_task_impl(
                    user_id,
                    keyword=keyword, scheduled_at=scheduled_iso, combo="",
                    energy_level=energy_level,
                    suggested_minutes=minutes,
                )
                created.append({
                    "task_id": row.get("id"),
                    "keyword": row.get("keyword"),
                    "minutes": row.get("default_minutes"),
                    "scheduled_at": row.get("scheduled_at"),
                    "status": row.get("status"),
                })
            else:
                row = _create_task_impl(
                    user_id,
                    keyword=keyword, combo="",
                    energy_level=energy_level,
                    suggested_minutes=minutes,
                    auto_start=False,
                )
                created.append({
                    "task_id": row.get("id"),
                    "keyword": row.get("keyword"),
                    "minutes": row.get("default_minutes"),
                    "scheduled_at": row.get("scheduled_at"),
                    "status": row.get("status"),
                })
        except Exception as e:
            logging.error(f"[PlanTool] create_tasks({keyword!r}) 失败: {type(e).__name__}: {e}")
            failed.append({"keyword": keyword, "reason": type(e).__name__})

    result: dict = {
        "ok": not failed,
        "created_count": len(created),
        "created_tasks": created,
    }
    if failed:
        result["failed"] = failed
    return result


_TOOL_IMPLS = {
    "query_tasks": _tool_query_tasks,
    "query_stats": _tool_query_stats,
    "query_schedule": _tool_query_schedule,
    "delete_task": _tool_delete_task,
    "delete_tasks": _tool_delete_tasks,
    "create_tasks": _tool_create_tasks,
}


def execute_tool(user_id: str, name: str, args: dict | None) -> str:
    """分发工具调用，返回 JSON 字符串给 DS。

    - 工具名不存在：返回 error JSON
    - 工具执行抛异常：捕获并返回 error JSON（不让 call_chat 崩）
    """
    args = args or {}
    impl = _TOOL_IMPLS.get(name)
    if impl is None:
        return json.dumps({"error": f"未知工具 {name}"}, ensure_ascii=False)
    try:
        result = impl(user_id, args)
    except Exception as e:
        logging.error(f"[PlanTool] {name} 执行失败: {type(e).__name__}: {e}")
        return json.dumps({"error": f"查询失败: {type(e).__name__}"}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False, default=str)
