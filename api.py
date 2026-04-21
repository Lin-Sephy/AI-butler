"""FastAPI 主入口，替代原 Streamlit app.py。

v2 多用户改造（2026-04-15）：
- 每个 endpoint 通过 Depends(get_current_user_id) 注入 user_id（从 JWT 解出）
- 所有 core/ 和 db/ 调用都传 user_id 作首参
- 启动时不再 spawn_daily_tasks（无 user context），改为按需在 /api/tasks/today 触发（idempotent）
"""

import logging
import uuid
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db.database import (
    init_db, save_action_log, get_user_memo, save_user_memo,
    clear_ai_memo, save_chat_message, load_session_messages, now_cn,
    get_companion_name, save_companion_name,
    get_custom_persona, save_custom_persona,
    get_companion_profile as db_get_companion_profile,
    get_daily_routine, save_daily_routine,
    create_project, list_projects, get_project, update_project, delete_project,
    get_tasks_recent, get_tasks_by_project,
)
from core.plan_tools import _tool_query_stats
from core.plan_extractor import extract_tasks_from_conversation
from core.auth import get_current_user_id
from core.memory import (
    update_ai_memory, get_filtered_daily_memo, bump_on_mention,
    get_confirmed_impressions_text, get_impressions_display,
)
from core.energy import get_current_energy, update_energy, ENERGY_LEVELS
from core.intent import call_chat
from core.task_manager import (
    create_task, pause_task, resume_task, complete_task, abandon_task,
    get_active_task, update_task_minutes, get_today_tasks, delete_task,
    create_recurring_task, get_recurring_tasks, delete_recurring_task,
    spawn_daily_tasks, start_task as tm_start_task,
    create_scheduled_task, get_scheduled_tasks, get_due_scheduled_tasks,
)

# ---------- App 初始化 ----------

app = FastAPI(title="AI 身体状态计划管家", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发阶段允许所有来源，部署时收紧
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],   # 包含 Authorization
)

init_db()
# 注意：spawn_daily_tasks 需要 user_id，不在启动时跑；放进 /api/tasks/today 按需触发


# ---------- 请求/响应模型 ----------

class ChatRequest(BaseModel):
    message: str
    session_id: str
    mode: str = "chat"  # "chat" | "plan"
    energy_level: int | None = None  # None 时自动获取当前精力


class ChatResponse(BaseModel):
    reply: str
    signal: dict
    task_recommendation: dict | None = None
    show_action_buttons: bool = False
    energy_confirm_needed: bool = False
    confirmed: bool = False  # v5 计划模式：DS 是否判定用户已定稿


class ProjectCreateRequest(BaseModel):
    name: str
    keywords: list[str] = []
    summary: str = ""


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    keywords: list[str] | None = None
    summary: str | None = None


class DailyRoutineRequest(BaseModel):
    routine: str


class PlanExtractRequest(BaseModel):
    session_id: str


class TaskActionRequest(BaseModel):
    task_id: int
    energy_level: int | None = None


class RecordTaskRequest(BaseModel):
    task_keyword: str
    suggested_minutes: int | None = None
    task_type: str = "work"
    detail: str = ""
    energy_level: int | None = None


class EnergyUpdateRequest(BaseModel):
    energy_level: int
    source: str = "manual"


class MemoRequest(BaseModel):
    content: str


class RecurringTaskRequest(BaseModel):
    keyword: str
    task_type: str = "work"
    default_minutes: int | None = 25


class ScheduledTaskRequest(BaseModel):
    keyword: str
    scheduled_at: str
    suggested_minutes: int | None = None
    task_type: str = "work"


class CompanionUpdateRequest(BaseModel):
    name: str | None = None
    custom_persona: str | None = None


# ---------- 辅助函数 ----------

def _build_task_board_text(user_id: str) -> str:
    """构建任务栏文本，传给 DS 聊天时参考。"""
    tasks = get_today_tasks(user_id)
    if not tasks:
        return ""
    parts = []
    executing = [t for t in tasks if t["status"] == "executing"]
    paused = [t for t in tasks if t["status"] == "paused"]
    completed = [t for t in tasks if t["status"] == "completed"]
    idle = [t for t in tasks if t["status"] == "idle"]
    if executing:
        parts.append("进行中：" + "、".join(t["keyword"] for t in executing))
    if paused:
        parts.append("已暂停：" + "、".join(t["keyword"] for t in paused))
    if idle:
        parts.append("待完成：" + "、".join(t["keyword"] for t in idle))
    if completed:
        parts.append("已完成：" + "、".join(t["keyword"] for t in completed))
    return " | ".join(parts)


# ---------- 聊天接口 ----------

@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, user_id: str = Depends(get_current_user_id)):
    """v5 聊天接口：闲聊 / 计划双模式。

    闲聊模式：DS 纯文本输出，无信号块，无推任务。
    计划模式：DS 注册 function calling 工具，可能输出 ---judgment---{"confirmed": true}。
    """
    mode = req.mode if req.mode in ("chat", "plan") else "chat"
    energy_level = req.energy_level or get_current_energy(user_id)["energy_level"]

    # 保存用户消息
    save_chat_message(user_id, req.session_id, "user", req.message)

    # 加载历史
    history = load_session_messages(user_id, req.session_id)
    history = history[:-1]  # 排除刚保存的这条

    # 读取跟宠名字和自定义人格
    profile = db_get_companion_profile(user_id)
    companion_name = profile["name"]
    custom_persona = profile["custom_persona"]

    # 聊天调用
    try:
        memo = get_user_memo(user_id)
        ai_memo_text = get_confirmed_impressions_text(user_id)
        daily_memo_text = get_filtered_daily_memo(user_id)
        task_board_text = _build_task_board_text(user_id)

        chat_result = call_chat(
            req.message, energy_level,
            chat_history=history,
            user_memo=memo, ai_memo=ai_memo_text,
            daily_memo=daily_memo_text,
            task_board=task_board_text,
            companion_name=companion_name,
            custom_persona=custom_persona,
            mode=mode,
            user_id=user_id,
        )
    except Exception as e:
        logging.error(f"聊天调用出错: {type(e).__name__}: {e}")
        chat_result = {"reply": "哎呀，出了点小问题。你再说一次？", "signal": {}, "confirmed": False}

    reply = chat_result["reply"]
    confirmed = chat_result.get("confirmed", False)

    # save_chat_message 走 INSERT 不走 upsert——等 reply 最终定版才写
    save_chat_message(user_id, req.session_id, "assistant", reply)

    # 关键词匹配（零 API 成本，闲聊模式下帮印象系统刷新计数）
    try:
        bump_on_mention(user_id, req.message)
    except Exception as e:
        logging.error(f"记忆关键词匹配失败: {type(e).__name__}: {e}")

    return ChatResponse(
        reply=reply,
        signal={},  # v5 无信号块，保留字段为了前端不破
        task_recommendation=None,
        show_action_buttons=False,
        energy_confirm_needed=False,
        confirmed=confirmed,
    )


# ---------- 计划结构化提取（v5） ----------

@app.post("/api/plan/extract")
def plan_extract(req: PlanExtractRequest, user_id: str = Depends(get_current_user_id)):
    """从对话中提取结构化 tasks，供前端展示让用户确认后批量写入。

    DS 输出 confirmed: true 后，前端调这个端点。返回候选 tasks 列表，
    前端让用户编辑（删除/改时长/改项目），确认后走 /api/task/record 批量写入。
    """
    history = load_session_messages(user_id, req.session_id)
    if not history:
        return {"tasks": []}
    tasks = extract_tasks_from_conversation(user_id, history)
    return {"tasks": tasks}


# ---------- 任务操作接口 ----------

@app.post("/api/task/record")
def record_task(req: RecordTaskRequest, user_id: str = Depends(get_current_user_id)):
    """记录任务到任务栏（idle 状态，不自动开始）。"""
    energy_level = req.energy_level or get_current_energy(user_id)["energy_level"]
    task = create_task(
        user_id,
        keyword=req.task_keyword, combo="",
        energy_level=energy_level,
        suggested_minutes=req.suggested_minutes,
        task_type=req.task_type,
        auto_start=False,
        detail=req.detail,
    )
    save_action_log(user_id, energy=energy_level,
                    recommendation=req.task_keyword, user_action="record")
    return {"message": f"已记录「{req.task_keyword}」", "task": task}


@app.post("/api/task/{task_id}/start")
def start(task_id: int, req: TaskActionRequest | None = None,
          user_id: str = Depends(get_current_user_id)):
    """开始一个 idle 或 scheduled 任务。"""
    energy_level = (req.energy_level if req else None) or get_current_energy(user_id)["energy_level"]
    try:
        task = tm_start_task(user_id, task_id, energy_level)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"message": f"开始「{task['keyword']}」！", "task": task}


@app.post("/api/task/{task_id}/pause")
def pause(task_id: int, user_id: str = Depends(get_current_user_id)):
    """暂停任务。"""
    task = pause_task(user_id, task_id)
    return {"message": f"「{task.get('keyword', '')}」已暂停", "task": task}


@app.post("/api/task/{task_id}/resume")
def resume(task_id: int, user_id: str = Depends(get_current_user_id)):
    """继续任务。"""
    task = resume_task(user_id, task_id)
    return {"message": f"继续「{task.get('keyword', '')}」！", "task": task}


@app.post("/api/task/{task_id}/complete")
def complete(task_id: int, user_id: str = Depends(get_current_user_id)):
    """完成任务。"""
    task = complete_task(user_id, task_id)
    save_action_log(user_id, recommendation=task.get("keyword", ""), user_action="complete")
    return {"message": f"「{task.get('keyword', '')}」完成了！", "task": task}


@app.post("/api/task/{task_id}/abandon")
def abandon(task_id: int, user_id: str = Depends(get_current_user_id)):
    """放弃任务。"""
    task = abandon_task(user_id, task_id)
    save_action_log(user_id, recommendation=task.get("keyword", ""), user_action="abandon")
    return {"message": f"「{task.get('keyword', '')}」已放弃", "task": task}


@app.post("/api/task/{task_id}/duration")
def change_duration(task_id: int, minutes: int, user_id: str = Depends(get_current_user_id)):
    """修改任务时长。"""
    task = update_task_minutes(user_id, task_id, minutes)
    return {"task": task}


@app.delete("/api/task/{task_id}")
def remove_task(task_id: int, user_id: str = Depends(get_current_user_id)):
    """删除任务。"""
    delete_task(user_id, task_id)
    return {"message": "已删除"}


# ---------- 任务查询接口 ----------

@app.get("/api/tasks/today")
def today_tasks(user_id: str = Depends(get_current_user_id)):
    """获取今日任务列表。顺带按需 spawn 今日循环任务（idempotent）。"""
    spawn_daily_tasks(user_id)
    return {"tasks": get_today_tasks(user_id)}


@app.get("/api/tasks/active")
def active_task(user_id: str = Depends(get_current_user_id)):
    """获取当前活跃任务。"""
    task = get_active_task(user_id)
    return {"task": task}


@app.get("/api/tasks/scheduled")
def scheduled_tasks(user_id: str = Depends(get_current_user_id)):
    """获取预定任务列表。"""
    return {"tasks": get_scheduled_tasks(user_id)}


@app.get("/api/tasks/due")
def due_tasks(user_id: str = Depends(get_current_user_id)):
    """获取到期的预定任务。"""
    return {"tasks": get_due_scheduled_tasks(user_id)}


@app.post("/api/tasks/scheduled")
def create_scheduled(req: ScheduledTaskRequest, user_id: str = Depends(get_current_user_id)):
    """创建预定任务。"""
    energy_level = get_current_energy(user_id)["energy_level"]
    task = create_scheduled_task(
        user_id,
        keyword=req.keyword, scheduled_at=req.scheduled_at,
        combo="", energy_level=energy_level,
        suggested_minutes=req.suggested_minutes, task_type=req.task_type,
    )
    return {"message": f"已预定「{req.keyword}」", "task": task}


# ---------- 循环任务接口 ----------

@app.get("/api/recurring")
def list_recurring(user_id: str = Depends(get_current_user_id)):
    """获取循环任务列表。"""
    return {"tasks": get_recurring_tasks(user_id)}


@app.post("/api/recurring")
def add_recurring(req: RecurringTaskRequest, user_id: str = Depends(get_current_user_id)):
    """创建循环任务。"""
    task = create_recurring_task(user_id, req.keyword, req.task_type, req.default_minutes)
    spawn_daily_tasks(user_id)   # 立即 spawn 今天的实例
    return {"message": f"已添加每日任务「{req.keyword}」", "task": task}


@app.delete("/api/recurring/{rec_id}")
def remove_recurring(rec_id: int, user_id: str = Depends(get_current_user_id)):
    """删除循环任务。"""
    delete_recurring_task(user_id, rec_id)
    return {"message": "已删除"}


# ---------- 精力系统接口 ----------

@app.get("/api/energy")
def get_energy(user_id: str = Depends(get_current_user_id)):
    """获取当前精力状态。"""
    energy = get_current_energy(user_id)
    level = energy["energy_level"]
    info = ENERGY_LEVELS[level]
    return {
        "energy_level": level,
        "source": energy["source"],
        "label": info["label"],
        "color": info["color"],
        "levels": {k: v for k, v in ENERGY_LEVELS.items()},
    }


@app.post("/api/energy")
def set_energy(req: EnergyUpdateRequest, user_id: str = Depends(get_current_user_id)):
    """手动设置精力值。"""
    update_energy(user_id, req.energy_level, req.source)
    level = req.energy_level
    info = ENERGY_LEVELS[level]
    return {
        "energy_level": level,
        "source": req.source,
        "label": info["label"],
        "color": info["color"],
    }


# ---------- 记忆库接口 ----------

@app.get("/api/memo/user")
def get_memo(user_id: str = Depends(get_current_user_id)):
    """获取用户手记。"""
    return {"content": get_user_memo(user_id)}


@app.post("/api/memo/user")
def save_memo(req: MemoRequest, user_id: str = Depends(get_current_user_id)):
    """保存用户手记。"""
    save_user_memo(user_id, req.content)
    return {"message": "已保存"}


@app.get("/api/memo/ai")
def get_ai_memory(user_id: str = Depends(get_current_user_id)):
    """获取 AI 记忆（展示用）。"""
    return {"content": get_impressions_display(user_id)}


@app.delete("/api/memo/ai")
def clear_ai_memory(user_id: str = Depends(get_current_user_id)):
    """清空 AI 记忆。"""
    clear_ai_memo(user_id)
    return {"message": "已清空"}


# ---------- 会话接口 ----------

@app.post("/api/session/new")
def new_session(user_id: str = Depends(get_current_user_id)):
    """创建新会话。"""
    session_id = str(uuid.uuid4())
    greeting = "来啦～"
    save_chat_message(user_id, session_id, "assistant", greeting)
    return {"session_id": session_id, "greeting": greeting}


@app.get("/api/session/{session_id}/messages")
def get_messages(session_id: str, user_id: str = Depends(get_current_user_id)):
    """获取会话历史消息。"""
    messages = load_session_messages(user_id, session_id)
    return {"messages": messages}


# ---------- 跟宠设置接口 ----------

CUSTOM_PERSONA_MAX_LENGTH = 1000


@app.get("/api/profile/companion")
def get_companion_endpoint(user_id: str = Depends(get_current_user_id)):
    """获取跟宠名字和自定义人格。"""
    return {
        "name": get_companion_name(user_id),
        "custom_persona": get_custom_persona(user_id),
        "max_persona_length": CUSTOM_PERSONA_MAX_LENGTH,
    }


@app.get("/api/profile/persona_presets")
def get_persona_presets():
    """返回 MBTI 三套预设文字（公开接口，不需要登录）。

    前端设置页点 MBTI 按钮时，把对应 key 的文字填进 custom_persona 输入框。
    用户可以原样保存、改动、或清空。
    """
    from prompts.system_prompt import PERSONAS
    return {
        "presets": [
            {"key": "infp", "label": "INFP", "text": PERSONAS["infp"]},
            {"key": "intj", "label": "INTJ", "text": PERSONAS["intj"]},
            {"key": "intp", "label": "INTP", "text": PERSONAS["intp"]},
        ],
        "max_length": CUSTOM_PERSONA_MAX_LENGTH,
    }


@app.put("/api/profile/companion")
def update_companion_profile(req: CompanionUpdateRequest,
                             user_id: str = Depends(get_current_user_id)):
    """更新跟宠名字和/或自定义人格。"""
    if req.name is not None:
        name = req.name.strip()
        if not name:
            raise HTTPException(400, "跟宠名字不能为空")
        if len(name) > 20:
            raise HTTPException(400, "跟宠名字不能超过 20 字")
        save_companion_name(user_id, name)

    if req.custom_persona is not None:
        persona = req.custom_persona.strip()
        if len(persona) > CUSTOM_PERSONA_MAX_LENGTH:
            raise HTTPException(400, f"自定义人格不能超过 {CUSTOM_PERSONA_MAX_LENGTH} 字")
        save_custom_persona(user_id, persona)

    return {
        "name": get_companion_name(user_id),
        "custom_persona": get_custom_persona(user_id),
        "message": "已更新",
    }


# ---------- 日常作息（v5） ----------

DAILY_ROUTINE_MAX_LENGTH = 500


@app.get("/api/profile/daily_routine")
def get_daily_routine_endpoint(user_id: str = Depends(get_current_user_id)):
    return {
        "routine": get_daily_routine(user_id),
        "max_length": DAILY_ROUTINE_MAX_LENGTH,
    }


@app.put("/api/profile/daily_routine")
def update_daily_routine(req: DailyRoutineRequest,
                         user_id: str = Depends(get_current_user_id)):
    routine = req.routine.strip()
    if len(routine) > DAILY_ROUTINE_MAX_LENGTH:
        raise HTTPException(400, f"日常作息不能超过 {DAILY_ROUTINE_MAX_LENGTH} 字")
    save_daily_routine(user_id, routine)
    return {"routine": routine, "message": "已更新"}


# ---------- 项目 CRUD（v5） ----------

PROJECT_NAME_MAX = 30
PROJECT_SUMMARY_MAX = 1000


@app.get("/api/projects")
def list_projects_endpoint(user_id: str = Depends(get_current_user_id)):
    return {"projects": list_projects(user_id)}


@app.post("/api/projects")
def create_project_endpoint(req: ProjectCreateRequest,
                            user_id: str = Depends(get_current_user_id)):
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "项目名不能为空")
    if len(name) > PROJECT_NAME_MAX:
        raise HTTPException(400, f"项目名不能超过 {PROJECT_NAME_MAX} 字")
    keywords = [k.strip() for k in (req.keywords or []) if k and k.strip()]
    summary = (req.summary or "").strip()
    if len(summary) > PROJECT_SUMMARY_MAX:
        raise HTTPException(400, f"项目摘要不能超过 {PROJECT_SUMMARY_MAX} 字")
    project = create_project(user_id, name, keywords, summary)
    return project


@app.patch("/api/projects/{project_id}")
def update_project_endpoint(project_id: int, req: ProjectUpdateRequest,
                            user_id: str = Depends(get_current_user_id)):
    existing = get_project(user_id, project_id)
    if not existing:
        raise HTTPException(404, "项目不存在")
    fields = {}
    if req.name is not None:
        name = req.name.strip()
        if not name:
            raise HTTPException(400, "项目名不能为空")
        if len(name) > PROJECT_NAME_MAX:
            raise HTTPException(400, f"项目名不能超过 {PROJECT_NAME_MAX} 字")
        fields["name"] = name
    if req.keywords is not None:
        fields["keywords"] = [k.strip() for k in req.keywords if k and k.strip()]
    if req.summary is not None:
        summary = req.summary.strip()
        if len(summary) > PROJECT_SUMMARY_MAX:
            raise HTTPException(400, f"项目摘要不能超过 {PROJECT_SUMMARY_MAX} 字")
        fields["summary"] = summary
    updated = update_project(user_id, project_id, **fields)
    return updated or existing


@app.delete("/api/projects/{project_id}")
def delete_project_endpoint(project_id: int,
                            user_id: str = Depends(get_current_user_id)):
    existing = get_project(user_id, project_id)
    if not existing:
        raise HTTPException(404, "项目不存在")
    delete_project(user_id, project_id)
    return {"message": "已删除"}


@app.get("/api/projects/{project_id}/tasks")
def list_project_tasks(project_id: int,
                       user_id: str = Depends(get_current_user_id)):
    existing = get_project(user_id, project_id)
    if not existing:
        raise HTTPException(404, "项目不存在")
    return {"tasks": get_tasks_by_project(user_id, project_id)}


# ---------- 任务历史 & 统计（v5） ----------

@app.get("/api/tasks/recent")
def recent_tasks(days: int = 7, user_id: str = Depends(get_current_user_id)):
    days = max(1, min(30, days))
    return {"days": days, "tasks": get_tasks_recent(user_id, days=days)}


@app.get("/api/stats")
def stats_endpoint(user_id: str = Depends(get_current_user_id)):
    """复用 plan_tools 里的统计逻辑，前端第 4 页也吃这个接口。"""
    return _tool_query_stats(user_id, {})
