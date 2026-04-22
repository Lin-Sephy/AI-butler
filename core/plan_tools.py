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
from datetime import datetime

from db.database import (
    get_tasks_recent,
    get_daily_routine,
    now_cn,
)
from core.task_manager import (
    delete_task as _delete_task_impl,
    create_task as _create_task_impl,
    create_scheduled_task as _create_scheduled_task_impl,
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
            "description": "查最近几天的任务记录明细（哪天做了什么、做了多久、完成没有）",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "查询最近多少天，默认 7",
                    },
                },
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
    days = args.get("days", 7)
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 7
    days = max(1, min(30, days))

    tasks = get_tasks_recent(user_id, days=days)
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
        }
        for t in tasks
    ]
    return {"days": days, "count": len(records), "records": records}


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

    # 最常专注时段（按 started_at 的小时分桶）
    hour_counter: Counter = Counter()
    for t in tasks:
        started = t.get("started_at")
        if started:
            try:
                dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                hour_counter[dt.hour] += 1
            except (ValueError, AttributeError):
                pass
    top_hours = hour_counter.most_common(3)
    top_hours_desc = [f"{h:02d}:00-{h + 1:02d}:00 ({n}次)" for h, n in top_hours] if top_hours else []

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
    """删除指定任务（限本人）。DS 只有在用户明确要取消时才应调。"""
    task_id = args.get("task_id")
    try:
        task_id = int(task_id)
    except (TypeError, ValueError):
        return {"error": "task_id 必须是整数"}

    try:
        _delete_task_impl(user_id, task_id)
    except Exception as e:
        logging.error(f"[PlanTool] delete_task({task_id}) 失败: {type(e).__name__}: {e}")
        return {"error": f"删除失败: {type(e).__name__}"}

    return {"ok": True, "deleted_task_id": task_id}


def _tool_delete_tasks(user_id: str, args: dict) -> dict:
    """批量删除任务。一次处理多条，省 function calling 轮数。"""
    raw = args.get("task_ids")
    if not isinstance(raw, list) or not raw:
        return {"error": "task_ids 必须是非空整数列表"}

    deleted: list[int] = []
    failed: list[dict] = []
    for item in raw:
        try:
            tid = int(item)
        except (TypeError, ValueError):
            failed.append({"task_id": item, "reason": "不是整数"})
            continue
        try:
            _delete_task_impl(user_id, tid)
            deleted.append(tid)
        except Exception as e:
            logging.error(f"[PlanTool] delete_tasks({tid}) 失败: {type(e).__name__}: {e}")
            failed.append({"task_id": tid, "reason": type(e).__name__})

    result: dict = {
        "ok": not failed,
        "deleted_count": len(deleted),
        "deleted_task_ids": deleted,
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

        try:
            if scheduled_iso:
                row = _create_scheduled_task_impl(
                    user_id,
                    keyword=keyword, scheduled_at=scheduled_iso, combo="",
                    energy_level=energy_level,
                    suggested_minutes=minutes,
                )
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
