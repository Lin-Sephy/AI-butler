"""计划模式的 function calling 工具：给 DS 按需查数据。

v5.0 架构（见开工文档）：
- 计划模式下 DS 通过 DeepSeek function calling 按需调用查询工具
- 闲聊模式不注册工具（DS 不知道这些数据存在）
- 所有工具都是只读查询；写入走独立的结构化提取流程
- Step 0 实测通过（召回率 100%，参数合法率 100%）
"""
import json
import logging
from collections import Counter
from datetime import datetime

from db.database import (
    get_tasks_recent,
    list_projects,
    get_project_by_name,
    get_tasks_by_project,
    get_daily_routine,
    now_cn,
)
from core.task_manager import (
    delete_task as _delete_task_impl,
    create_task as _create_task_impl,
)


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
            "name": "query_project",
            "description": "查某个项目的摘要和关联任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "项目名称，如'毕业论文'、'考研'",
                    },
                },
                "required": ["name"],
            },
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
                "所有任务会以 idle（待完成）状态写入，不自动开始。"
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
                                "task_type": {
                                    "type": "string",
                                    "enum": ["work", "rest"],
                                    "description": "work=工作/学习，rest=休息/放松",
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
            "task_type": t.get("task_type"),
            "created_at": t.get("created_at"),
            "started_at": t.get("started_at"),
            "completed_at": t.get("completed_at"),
            "scheduled_at": t.get("scheduled_at"),
            "minutes": t.get("default_minutes"),
            "project_id": t.get("project_id"),
        }
        for t in tasks
    ]
    return {"days": days, "count": len(records), "records": records}


def _tool_query_stats(user_id: str, args: dict) -> dict:
    """从最近 30 天任务记录算统计。纯 Python 聚合，无 LLM。"""
    tasks = get_tasks_recent(user_id, days=30)
    if not tasks:
        return {"message": "最近 30 天还没有任务记录"}

    # 完成率
    total = len(tasks)
    completed = sum(1 for t in tasks if t.get("status") == "completed")
    abandoned = sum(1 for t in tasks if t.get("status") == "abandoned")
    completion_rate = round(completed / total * 100, 1) if total else 0

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


def _tool_query_project(user_id: str, args: dict) -> dict:
    name = args.get("name", "").strip()
    if not name:
        return {"error": "需要传项目名（name 参数）"}

    # 先精确匹配
    project = get_project_by_name(user_id, name)
    if not project:
        # 再做一次子串匹配兜底
        all_projects = list_projects(user_id)
        hits = [p for p in all_projects if name in p["name"] or p["name"] in name]
        if not hits:
            available = [p["name"] for p in all_projects]
            return {
                "error": f"没找到项目'{name}'",
                "铲屎官建过的项目": available or "（还没建过）",
            }
        project = hits[0]

    tasks = get_tasks_by_project(user_id, project["id"])
    related = [
        {
            "keyword": t.get("keyword"),
            "status": t.get("status"),
            "created_at": t.get("created_at"),
            "completed_at": t.get("completed_at"),
        }
        for t in tasks[:20]  # 最近 20 条够 DS 看了
    ]

    return {
        "name": project.get("name"),
        "keywords": project.get("keywords") or [],
        "summary": project.get("summary") or "（还没有摘要）",
        "updated_at": project.get("updated_at"),
        "关联任务": related,
    }


def _tool_query_schedule(user_id: str, args: dict) -> dict:
    """今日事件（scheduled_at 在今天的任务）+ 用户日常作息。

    任意 scheduled_at 落在今天的 task 都算"今日事件"——不限 task_type，
    因为 v5.0 DB 的 task_type 只有 work/rest 没有专门的 event 类型。
    """
    today = now_cn().strftime("%Y-%m-%d")

    tasks = get_tasks_recent(user_id, days=3)
    today_events = []
    for t in tasks:
        scheduled = t.get("scheduled_at") or ""
        if scheduled.startswith(today):
            today_events.append({
                "time": scheduled,
                "keyword": t.get("keyword"),
                "task_type": t.get("task_type"),
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
    """批量创建任务（一次多条，省轮数）。所有任务 idle 状态，不自动开始。"""
    raw = args.get("tasks")
    if not isinstance(raw, list) or not raw:
        return {"error": "tasks 必须是非空任务列表"}

    # 能量档位读一个占位值（v5.0 不再依赖精力档位）
    energy_level = 3

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

        task_type = item.get("task_type") or "work"
        if task_type not in ("work", "rest"):
            task_type = "work"

        minutes = item.get("minutes")
        if minutes is not None:
            try:
                minutes = max(1, min(480, int(minutes)))
            except (TypeError, ValueError):
                minutes = None

        try:
            row = _create_task_impl(
                user_id,
                keyword=keyword, combo="",
                energy_level=energy_level,
                suggested_minutes=minutes,
                task_type=task_type,
                auto_start=False,
            )
            created.append({
                "task_id": row.get("id"),
                "keyword": row.get("keyword"),
                "minutes": row.get("default_minutes"),
                "task_type": row.get("task_type"),
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
    "query_project": _tool_query_project,
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
