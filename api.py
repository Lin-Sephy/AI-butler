"""FastAPI 主入口，替代原 Streamlit app.py。"""

import logging
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db.database import (
    init_db, save_action_log, get_user_memo, save_user_memo,
    clear_ai_memo, save_chat_message, load_session_messages, now_cn,
    get_companion_name, save_companion_name,
    get_custom_persona, save_custom_persona,
    get_companion_profile,
)
from core.memory import (
    update_ai_memory, get_filtered_daily_memo, bump_on_mention,
    get_confirmed_impressions_text, get_impressions_display,
)
from core.energy import get_current_energy, update_energy, ENERGY_LEVELS
from core.intent import call_chat, call_task
from core.rules_engine import (
    validate_reply, check_energy_drift, should_trigger_task,
    should_show_action_buttons, find_matching_task,
)
from core.task_manager import (
    create_task, pause_task, resume_task, complete_task, abandon_task,
    get_active_task, update_task_minutes, get_today_tasks, delete_task,
    create_recurring_task, get_recurring_tasks, delete_recurring_task,
    spawn_daily_tasks, start_idle_task,
    create_scheduled_task, get_scheduled_tasks, get_due_scheduled_tasks,
    start_scheduled_task,
)

# ---------- App 初始化 ----------

app = FastAPI(title="AI 身体状态计划管家", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发阶段允许所有来源，部署时收紧
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
spawn_daily_tasks()


# ---------- 请求/响应模型 ----------

class ChatRequest(BaseModel):
    message: str
    session_id: str
    persona: str = "intj"
    energy_level: int | None = None  # None 时自动获取当前精力


class ChatResponse(BaseModel):
    reply: str
    signal: dict
    task_recommendation: dict | None = None
    show_action_buttons: bool = False
    energy_confirm_needed: bool = False


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

def _build_task_board_text() -> str:
    """构建任务栏文本，传给 DS 聊天时参考。"""
    tasks = get_today_tasks()
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
def chat(req: ChatRequest):
    """核心聊天接口：聊天 → 信号解析 → 是否推任务 → 返回结果。"""
    energy_level = req.energy_level or get_current_energy()["energy_level"]

    # 保存用户消息
    save_chat_message(req.session_id, "user", req.message)

    # 加载历史
    history = load_session_messages(req.session_id)
    history = history[:-1]  # 排除刚保存的这条

    # 读取跟宠名字和自定义人格（一次查询拿两个字段）
    profile = get_companion_profile()
    companion_name = profile["name"]
    custom_persona = profile["custom_persona"]

    # 聊天调用
    try:
        memo = get_user_memo()
        ai_memo_text = get_confirmed_impressions_text()
        daily_memo_text = get_filtered_daily_memo()
        task_board_text = _build_task_board_text()

        chat_result = call_chat(
            req.message, energy_level,
            chat_history=history,
            persona=req.persona,
            user_memo=memo, ai_memo=ai_memo_text,
            daily_memo=daily_memo_text,
            task_board=task_board_text,
            companion_name=companion_name,
            custom_persona=custom_persona,
        )
    except Exception as e:
        logging.error(f"聊天调用出错: {type(e).__name__}: {e}")
        chat_result = {"reply": "哎呀，出了点小问题。你再说一次？", "signal": {}}

    signal = chat_result.get("signal", {})
    reply = chat_result["reply"]

    # 保存 AI 回复
    save_chat_message(req.session_id, "assistant", reply)

    # 精力偏差检测
    _, energy_confirm_needed = check_energy_drift(signal, energy_level)

    # Python 判断是否触发推任务
    today_tasks = get_today_tasks()
    trigger = should_trigger_task(signal, energy_level, today_tasks)

    task_recommendation = None
    show_buttons = False

    if trigger:
        try:
            done_tasks = [t["keyword"] for t in today_tasks if t["status"] == "completed"]
            recent_context = "\n".join(
                f"{'用户' if m['role'] == 'user' else companion_name}: {m['content']}"
                for m in (history or [])[-6:]
            )
            task_resp = call_task(
                req.message, energy_level,
                chat_history=history,
                persona=req.persona,
                completed_tasks=done_tasks if done_tasks else None,
                context=recent_context,
                companion_name=companion_name,
                custom_persona=custom_persona,
            )

            is_valid, final_reply = validate_reply(task_resp, energy_level)
            if not is_valid:
                task_resp["reply"] = final_reply

            if task_resp.get("reply"):
                reply = task_resp["reply"]
                # 更新数据库中的 AI 回复
                save_chat_message(req.session_id, "assistant", reply)

            if should_show_action_buttons(task_resp):
                show_buttons = True
                task_recommendation = task_resp

        except Exception as e:
            logging.error(f"任务推荐调用出错: {type(e).__name__}: {e}")

    # 关键词匹配（零 API 成本）
    try:
        bump_on_mention(req.message)
    except Exception as e:
        logging.error(f"记忆关键词匹配失败: {type(e).__name__}: {e}")

    return ChatResponse(
        reply=reply,
        signal=signal,
        task_recommendation=task_recommendation,
        show_action_buttons=show_buttons,
        energy_confirm_needed=energy_confirm_needed,
    )


# ---------- 任务操作接口 ----------

@app.post("/api/task/record")
def record_task(req: RecordTaskRequest):
    """记录任务到任务栏（idle 状态，不自动开始）。"""
    energy_level = req.energy_level or get_current_energy()["energy_level"]
    task = create_task(
        keyword=req.task_keyword, combo="",
        energy_level=energy_level,
        suggested_minutes=req.suggested_minutes,
        task_type=req.task_type,
        auto_start=False,
        detail=req.detail,
    )
    save_action_log(energy=energy_level, intent="", strategy="",
                    recommendation=req.task_keyword, user_action="record")
    return {"message": f"已记录「{req.task_keyword}」", "task": task}


@app.post("/api/task/{task_id}/start")
def start_task(task_id: int, req: TaskActionRequest | None = None):
    """开始一个 idle 或 scheduled 任务。"""
    energy_level = (req.energy_level if req else None) or get_current_energy()["energy_level"]
    try:
        task = start_idle_task(task_id, energy_level)
        return {"message": f"开始「{task['keyword']}」！", "task": task}
    except ValueError:
        try:
            task = start_scheduled_task(task_id, energy_level)
            return {"message": f"开始「{task['keyword']}」！", "task": task}
        except ValueError:
            raise HTTPException(400, "已有执行中的任务，请先完成或放弃")


@app.post("/api/task/{task_id}/pause")
def pause(task_id: int):
    """暂停任务。"""
    task = pause_task(task_id)
    return {"message": f"「{task.get('keyword', '')}」已暂停", "task": task}


@app.post("/api/task/{task_id}/resume")
def resume(task_id: int):
    """继续任务。"""
    task = resume_task(task_id)
    return {"message": f"继续「{task.get('keyword', '')}」！", "task": task}


@app.post("/api/task/{task_id}/complete")
def complete(task_id: int):
    """完成任务。"""
    task = complete_task(task_id)
    save_action_log(energy=0, intent="", strategy="",
                    recommendation=task.get("keyword", ""), user_action="complete")
    return {"message": f"「{task.get('keyword', '')}」完成了！", "task": task}


@app.post("/api/task/{task_id}/abandon")
def abandon(task_id: int):
    """放弃任务。"""
    task = abandon_task(task_id)
    save_action_log(energy=0, intent="", strategy="",
                    recommendation=task.get("keyword", ""), user_action="abandon")
    return {"message": f"「{task.get('keyword', '')}」已放弃", "task": task}


@app.post("/api/task/{task_id}/duration")
def change_duration(task_id: int, minutes: int):
    """修改任务时长。"""
    task = update_task_minutes(task_id, minutes)
    return {"task": task}


@app.delete("/api/task/{task_id}")
def remove_task(task_id: int):
    """删除任务。"""
    delete_task(task_id)
    return {"message": "已删除"}


# ---------- 任务查询接口 ----------

@app.get("/api/tasks/today")
def today_tasks():
    """获取今日任务列表。"""
    return {"tasks": get_today_tasks()}


@app.get("/api/tasks/active")
def active_task():
    """获取当前活跃任务。"""
    task = get_active_task()
    return {"task": task}


@app.get("/api/tasks/scheduled")
def scheduled_tasks():
    """获取预定任务列表。"""
    return {"tasks": get_scheduled_tasks()}


@app.get("/api/tasks/due")
def due_tasks():
    """获取到期的预定任务。"""
    return {"tasks": get_due_scheduled_tasks()}


@app.post("/api/tasks/scheduled")
def create_scheduled(req: ScheduledTaskRequest):
    """创建预定任务。"""
    energy_level = get_current_energy()["energy_level"]
    task = create_scheduled_task(
        keyword=req.keyword, scheduled_at=req.scheduled_at,
        combo="", energy_level=energy_level,
        suggested_minutes=req.suggested_minutes, task_type=req.task_type,
    )
    return {"message": f"已预定「{req.keyword}」", "task": task}


# ---------- 循环任务接口 ----------

@app.get("/api/recurring")
def list_recurring():
    """获取循环任务列表。"""
    return {"tasks": get_recurring_tasks()}


@app.post("/api/recurring")
def add_recurring(req: RecurringTaskRequest):
    """创建循环任务。"""
    task = create_recurring_task(req.keyword, req.task_type, req.default_minutes)
    spawn_daily_tasks()
    return {"message": f"已添加每日任务「{req.keyword}」", "task": task}


@app.delete("/api/recurring/{rec_id}")
def remove_recurring(rec_id: int):
    """删除循环任务。"""
    delete_recurring_task(rec_id)
    return {"message": "已删除"}


# ---------- 精力系统接口 ----------

@app.get("/api/energy")
def get_energy():
    """获取当前精力状态。"""
    energy = get_current_energy()
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
def set_energy(req: EnergyUpdateRequest):
    """手动设置精力值。"""
    update_energy(req.energy_level, req.source)
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
def get_memo():
    """获取用户手记。"""
    return {"content": get_user_memo()}


@app.post("/api/memo/user")
def save_memo(req: MemoRequest):
    """保存用户手记。"""
    save_user_memo(req.content)
    return {"message": "已保存"}


@app.get("/api/memo/ai")
def get_ai_memory():
    """获取 AI 记忆（展示用）。"""
    return {"content": get_impressions_display()}


@app.delete("/api/memo/ai")
def clear_ai_memory():
    """清空 AI 记忆。"""
    clear_ai_memo()
    return {"message": "已清空"}


# ---------- 会话接口 ----------

@app.post("/api/session/new")
def new_session():
    """创建新会话。"""
    session_id = str(uuid.uuid4())
    greeting = "来啦～"
    save_chat_message(session_id, "assistant", greeting)
    return {"session_id": session_id, "greeting": greeting}


@app.get("/api/session/{session_id}/messages")
def get_messages(session_id: str):
    """获取会话历史消息。"""
    messages = load_session_messages(session_id)
    return {"messages": messages}


# ---------- 跟宠设置接口 ----------

CUSTOM_PERSONA_MAX_LENGTH = 200


@app.get("/api/profile/companion")
def get_companion_profile():
    """获取跟宠名字和自定义人格。"""
    return {
        "name": get_companion_name(),
        "custom_persona": get_custom_persona(),
        "max_persona_length": CUSTOM_PERSONA_MAX_LENGTH,
    }


@app.put("/api/profile/companion")
def update_companion_profile(req: CompanionUpdateRequest):
    """更新跟宠名字和/或自定义人格。"""
    if req.name is not None:
        name = req.name.strip()
        if not name:
            raise HTTPException(400, "跟宠名字不能为空")
        if len(name) > 20:
            raise HTTPException(400, "跟宠名字不能超过 20 字")
        save_companion_name(name)

    if req.custom_persona is not None:
        persona = req.custom_persona.strip()
        if len(persona) > CUSTOM_PERSONA_MAX_LENGTH:
            raise HTTPException(400, f"自定义人格不能超过 {CUSTOM_PERSONA_MAX_LENGTH} 字")
        save_custom_persona(persona)

    return {
        "name": get_companion_name(),
        "custom_persona": get_custom_persona(),
        "message": "已更新",
    }
