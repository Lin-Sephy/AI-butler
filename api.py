"""FastAPI 主入口，替代原 Streamlit app.py。

v2 多用户改造（2026-04-15）：
- 每个 endpoint 通过 Depends(get_current_user_id) 注入 user_id（从 JWT 解出）
- 所有 core/ 和 db/ 调用都传 user_id 作首参
- 启动时不再 spawn_daily_tasks（无 user context），改为按需在 /api/tasks/today 触发（idempotent）
"""

import logging
import os
import uuid
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db.database import (
    init_db, save_action_log, get_user_memo, save_user_memo,
    clear_ai_memo, save_chat_message, load_session_messages, now_cn,
    get_companion_name, save_companion_name,
    get_custom_persona, save_custom_persona,
    get_companion_profile as db_get_companion_profile,
    get_full_profile, get_llm_config, save_llm_config,
    get_daily_routine, save_daily_routine,
    create_project, list_projects, get_project, update_project, delete_project,
    get_tasks_recent, get_tasks_by_project, get_completed_tasks_all,
)
from core.plan_tools import _tool_query_stats
from core.auth import get_current_user_id
from core.memory import (
    update_ai_memory, get_filtered_daily_memo, bump_on_mention,
    get_confirmed_impressions_text, get_impressions_display,
)
from core.intent import call_chat
from core.task_manager import (
    create_task, pause_task, resume_task, complete_task, abandon_task,
    get_active_task, update_task_minutes, update_task_keyword,
    get_today_tasks, delete_task, restore_task,
    create_recurring_task, get_recurring_tasks, delete_recurring_task,
    spawn_daily_tasks, start_task as tm_start_task,
    create_scheduled_task, get_scheduled_tasks, get_due_scheduled_tasks,
)

# ---------- App 初始化 ----------

app = FastAPI(title="AI 身体状态计划管家", version="2.0.0")

# CORS 允许来源：读环境变量 ALLOWED_ORIGINS 白名单，逗号分隔。
# 不配或配 "*" 时退回全放（本地开发方便；生产必须配具体域名，如 Vercel 前端 URL）
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*").strip()
if _raw_origins == "*":
    _allowed_origins = ["*"]
else:
    _allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],   # 包含 Authorization
)

init_db()
# 注意：spawn_daily_tasks 需要 user_id，不在启动时跑；放进 /api/tasks/today 按需触发


# ---------- 健康检查（Supabase 保活） ----------

@app.get("/api/health")
def health_check():
    """轻量健康检查：查一次 Supabase 防 7 天暂停。"""
    from db.database import _get
    try:
        _get("user_profile", {"select": "user_id", "limit": "1"})
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return {"status": "ok", "db": f"error: {e}"}


# ---------- 请求/响应模型 ----------

class ChatRequest(BaseModel):
    message: str
    session_id: str
    mode: str = "chat"  # "chat" | "plan"


class ChatResponse(BaseModel):
    reply: str
    confirmed: bool = False  # v5 计划模式：DS 是否判定用户已定稿
    created_tasks: list[dict] = []  # v5 计划模式：本轮 create_tasks 工具写入的任务，前端弹窗用
    pending_deletes: list[dict] = []  # v5 计划模式：本轮 delete_task(s) 待确认删除，前端弹窗用


class SessionNoteRequest(BaseModel):
    content: str
    mode: str = "plan"


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


class TaskActionRequest(BaseModel):
    task_id: int


class RecordTaskRequest(BaseModel):
    task_keyword: str
    suggested_minutes: int | None = None
    task_type: str = "work"
    detail: str = ""


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
def chat(req: ChatRequest, background_tasks: BackgroundTasks,
         user_id: str = Depends(get_current_user_id)):
    """v5 聊天接口：闲聊 / 计划双模式。

    闲聊模式：DS 纯文本输出，无信号块，无推任务。
    计划模式：DS 注册 function calling 工具，可能输出 ---judgment---{"confirmed": true}。
    """
    mode = req.mode if req.mode in ("chat", "plan") else "chat"

    # 保存用户消息（带当前 mode 标签，供后续按 mode 分流加载）
    save_chat_message(user_id, req.session_id, "user", req.message, mode)

    # 加载历史 · 非对称过滤：
    # - 闲聊模式：只拉 mode='chat'，防止 DS 看到 plan 模式 tool call 结果
    #   然后幻觉出"你任务栏有 XX"这种不存在的事
    # - 任务模式：拉全部（闲聊 + 任务），DS 需要完整上下文来排任务
    history_mode = "chat" if mode == "chat" else None
    history = load_session_messages(user_id, req.session_id, mode=history_mode)
    history = history[:-1]  # 排除刚保存的这条

    # 一次性 SELECT * 读 user_profile 所有字段，分发给各处用——替代原本的 4 次独立查询
    full_profile = get_full_profile(user_id)
    companion_name = full_profile.get("companion_name", "小白")
    custom_persona = full_profile.get("custom_persona", "")

    # BYOK：用户自带 LLM 配置（完整时会走用户自己的，否则回退默认 DeepSeek）
    user_llm = {
        "provider": full_profile.get("llm_provider", ""),
        "base_url": full_profile.get("llm_base_url", ""),
        "model": full_profile.get("llm_model", ""),
        "api_key": full_profile.get("llm_api_key", ""),
    }

    # 聊天调用
    try:
        memo = full_profile.get("user_memo", "")
        ai_memo_text = get_confirmed_impressions_text(
            user_id, ai_memo_raw=full_profile.get("ai_memo", "")
        )
        daily_memo_text = get_filtered_daily_memo(
            user_id, daily_memo_raw=full_profile.get("daily_memo", "{}")
        )
        # v5 任务栏不预喂：闲聊模式不聊任务，计划模式 DS 用 query_tasks 按需查（更精准）
        task_board_text = ""

        chat_result = call_chat(
            req.message,
            chat_history=history,
            user_memo=memo, ai_memo=ai_memo_text,
            daily_memo=daily_memo_text,
            task_board=task_board_text,
            companion_name=companion_name,
            custom_persona=custom_persona,
            mode=mode,
            user_id=user_id,
            user_llm=user_llm,
        )
    except Exception as e:
        logging.error(f"聊天调用出错: {type(e).__name__}: {e}")
        chat_result = {"reply": "哎呀，出了点小问题。你再说一次？", "confirmed": False}

    reply = chat_result["reply"]
    confirmed = chat_result.get("confirmed", False)

    # save_chat_message 走 INSERT 不走 upsert——等 reply 最终定版才写
    save_chat_message(user_id, req.session_id, "assistant", reply, mode)

    # 关键词匹配（零 API 成本，闲聊模式下帮印象系统刷新计数）
    try:
        bump_on_mention(user_id, req.message)
    except Exception as e:
        logging.error(f"记忆关键词匹配失败: {type(e).__name__}: {e}")

    # AI 记忆提取：每 20 轮用户消息异步跑一次（不阻塞响应）
    # 20 刚好对齐 call_chat 里塞给 DS 的"最近 20 条对话"窗口——
    # 每滚完一个窗口就让印象系统复盘一次，成本和幻觉都低
    try:
        full_history = load_session_messages(user_id, req.session_id)
        user_count = sum(1 for m in full_history if m.get("role") == "user")
        if user_count > 0 and user_count % 20 == 0:
            background_tasks.add_task(update_ai_memory, user_id, full_history)
    except Exception as e:
        logging.error(f"记忆更新调度失败: {type(e).__name__}: {e}")

    return ChatResponse(
        reply=reply,
        confirmed=confirmed,
        created_tasks=chat_result.get("created_tasks") or [],
        pending_deletes=chat_result.get("pending_deletes") or [],
    )


# ---------- 任务操作接口 ----------

@app.post("/api/task/record")
def record_task(req: RecordTaskRequest, user_id: str = Depends(get_current_user_id)):
    """记录任务到任务栏（idle 状态，不自动开始）。"""
    task = create_task(
        user_id,
        keyword=req.task_keyword, combo="",
        suggested_minutes=req.suggested_minutes,
        task_type=req.task_type,
        auto_start=False,
        detail=req.detail,
    )
    save_action_log(user_id, recommendation=req.task_keyword, user_action="record")
    return {"message": f"已记录「{req.task_keyword}」", "task": task}


@app.post("/api/task/{task_id}/start")
def start(task_id: int, req: TaskActionRequest | None = None,
          user_id: str = Depends(get_current_user_id)):
    """开始一个 idle 或 scheduled 任务。"""
    try:
        task = tm_start_task(user_id, task_id)
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


@app.post("/api/task/{task_id}/restore")
def restore(task_id: int, user_id: str = Depends(get_current_user_id)):
    """把 abandoned 任务恢复成 idle，重置 created_at。"""
    task = restore_task(user_id, task_id)
    if not task:
        raise HTTPException(404, "任务不存在或不在已放弃状态")
    return {"message": f"「{task.get('keyword', '')}」已恢复", "task": task}


@app.post("/api/task/{task_id}/duration")
def change_duration(task_id: int, minutes: int, user_id: str = Depends(get_current_user_id)):
    """修改任务时长。"""
    task = update_task_minutes(user_id, task_id, minutes)
    return {"task": task}


class KeywordUpdateRequest(BaseModel):
    keyword: str


@app.post("/api/task/{task_id}/keyword")
def change_keyword(task_id: int, req: KeywordUpdateRequest,
                   user_id: str = Depends(get_current_user_id)):
    """修改任务名。"""
    keyword = req.keyword.strip()
    if not keyword:
        raise HTTPException(400, "任务名不能为空")
    if len(keyword) > 100:
        raise HTTPException(400, "任务名不能超过 100 字")
    task = update_task_keyword(user_id, task_id, keyword)
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
    task = create_scheduled_task(
        user_id,
        keyword=req.keyword, scheduled_at=req.scheduled_at,
        combo="",
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


@app.delete("/api/task/{task_id}/recurring")
def stop_recurring_by_task(task_id: int, user_id: str = Depends(get_current_user_id)):
    """通过今日任务副本停掉对应的循环模板，并删除该副本。"""
    from core.task_manager import _get_task_by_id
    task = _get_task_by_id(user_id, task_id)
    if not task or task.get("combo") != "recurring":
        raise HTTPException(404, "不是循环任务")
    keyword = task.get("keyword")
    recs = get_recurring_tasks(user_id)
    stopped = False
    for rec in recs:
        if rec.get("keyword") == keyword:
            delete_recurring_task(user_id, rec["id"])
            stopped = True
    delete_task(user_id, task_id)
    return {"message": f"已停止每日「{keyword}」", "stopped": stopped}


# ---------- 记忆库接口 ----------

USER_MEMO_MAX_LENGTH = 2000


@app.get("/api/memo/user")
def get_memo(user_id: str = Depends(get_current_user_id)):
    """获取用户手记。"""
    return {
        "content": get_user_memo(user_id),
        "max_length": USER_MEMO_MAX_LENGTH,
    }


@app.post("/api/memo/user")
def save_memo(req: MemoRequest, user_id: str = Depends(get_current_user_id)):
    """保存用户手记。"""
    if len(req.content) > USER_MEMO_MAX_LENGTH:
        raise HTTPException(400, f"用户手记不能超过 {USER_MEMO_MAX_LENGTH} 字")
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
    save_chat_message(user_id, session_id, "assistant", greeting, "chat")
    return {"session_id": session_id, "greeting": greeting}


@app.get("/api/session/{session_id}/messages")
def get_messages(session_id: str, user_id: str = Depends(get_current_user_id)):
    """获取会话历史消息。"""
    messages = load_session_messages(user_id, session_id)
    return {"messages": [m for m in messages if m.get("role") != "system_note"]}


@app.post("/api/session/{session_id}/note")
def add_session_note(session_id: str, req: SessionNoteRequest,
                     user_id: str = Depends(get_current_user_id)):
    """写入只给模型看的会话事件，不在前端历史里展示。"""
    content = req.content.strip()
    if not content:
        raise HTTPException(400, "记录内容不能为空")
    mode = req.mode if req.mode in ("chat", "plan") else "plan"
    save_chat_message(user_id, session_id, "system_note", content, mode)
    return {"message": "已记录"}


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


# ---------- BYOK：用户自带 LLM API key ----------

class LLMConfigRequest(BaseModel):
    provider: str = ""
    base_url: str = ""
    model: str = ""
    api_key: str = ""  # 空串 = 不更新 api_key（保留原值）；非空 = 新 key


def _mask_api_key(key: str) -> str:
    """掩码展示 api_key，前端不能拿到明文。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "••••••••"
    return "••••••••" + key[-4:]


@app.get("/api/profile/llm")
def get_llm_config_endpoint(user_id: str = Depends(get_current_user_id)):
    """返回用户 LLM 配置。api_key 字段只展示掩码（前 • 后 4 位），不回显明文。"""
    cfg = get_llm_config(user_id)
    return {
        "provider": cfg["provider"],
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "api_key_hint": _mask_api_key(cfg["api_key"]),
        "has_key": bool(cfg["api_key"]),
    }


@app.put("/api/profile/llm")
def update_llm_config_endpoint(req: LLMConfigRequest,
                               user_id: str = Depends(get_current_user_id)):
    """更新用户 LLM 配置。api_key 空串表示不改（保留原值），非空表示覆盖。"""
    provider = req.provider.strip()
    base_url = req.base_url.strip()
    model = req.model.strip()
    api_key = req.api_key.strip()

    # 长度校验
    if len(provider) > 30:
        raise HTTPException(400, "服务商名字不能超过 30 字")
    if len(base_url) > 200:
        raise HTTPException(400, "Base URL 不能超过 200 字")
    if len(model) > 100:
        raise HTTPException(400, "Model 不能超过 100 字")
    if len(api_key) > 200:
        raise HTTPException(400, "API key 不能超过 200 字")

    save_llm_config(
        user_id, provider, base_url, model,
        api_key=api_key if api_key else None,
    )
    cfg = get_llm_config(user_id)
    return {
        "provider": cfg["provider"],
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "api_key_hint": _mask_api_key(cfg["api_key"]),
        "has_key": bool(cfg["api_key"]),
        "message": "已更新",
    }


@app.delete("/api/profile/llm")
def clear_llm_config_endpoint(user_id: str = Depends(get_current_user_id)):
    """清空用户 LLM 配置，回退到默认 DeepSeek。"""
    save_llm_config(user_id, "", "", "", api_key="")
    return {"message": "已清空，将使用默认服务"}


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


@app.get("/api/stats/dashboard")
def stats_dashboard(user_id: str = Depends(get_current_user_id)):
    """数据页一次性聚合：今日 / 任务分布（日周月）/ 24h 桶 / 30 天每日 / 累计。

    不供 DS tool call 使用（那条走 /api/stats → _tool_query_stats，只返分布）。
    纯 Python 聚合，不调 DS。所有时间戳统一转成北京时间后再聚合/比较。"""
    from collections import Counter, defaultdict
    from datetime import datetime, timedelta, timezone

    CN_TZ = timezone(timedelta(hours=8))

    def to_cn(iso):
        """ISO 时间字符串 → aware datetime（北京时间）。
        Supabase 返回可能是 UTC 带 Z，不转时区直接聚合会偏 8 小时。"""
        if not iso:
            return None
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=CN_TZ)
            else:
                dt = dt.astimezone(CN_TZ)
            return dt
        except (ValueError, AttributeError):
            return None

    tasks_30d = [t for t in get_tasks_recent(user_id, days=30) if (t.get("default_minutes") or 0) >= 1]
    tasks_all = [t for t in get_completed_tasks_all(user_id) if (t.get("default_minutes") or 0) >= 1]

    now = now_cn()
    today_str = now.strftime("%Y-%m-%d")
    week_cutoff_dt = now - timedelta(days=7)

    # ---- 时区归一的日期/时段工具 ----
    def cn_date(t, field):
        dt = to_cn(t.get(field))
        return dt.strftime("%Y-%m-%d") if dt else None

    def is_today(t):
        return cn_date(t, "completed_at") == today_str

    def is_this_week(t):
        dt = to_cn(t.get("completed_at"))
        return dt is not None and dt >= week_cutoff_dt

    # ---- today ----
    today_done = [
        t for t in tasks_30d
        if t.get("status") == "completed" and is_today(t)
    ]
    today_minutes = sum((t.get("default_minutes") or 0) for t in today_done)
    today_kw = Counter(t["keyword"] for t in today_done if t.get("keyword"))
    today_top = today_kw.most_common(1)[0][0] if today_kw else None

    today_data = {
        "total_minutes": today_minutes,
        "tasks_completed": len(today_done),
        "top_keyword": today_top,
    }

    # ---- distribution (day/week/month) ----
    def distribution_for(predicate):
        filtered = [
            t for t in tasks_30d
            if t.get("status") == "completed" and predicate(t)
        ]
        counter: Counter = Counter()
        for t in filtered:
            kw = t.get("keyword")
            if kw:
                counter[kw] += (t.get("default_minutes") or 0)
        total = sum(counter.values())
        items = [
            {
                "keyword": k,
                "minutes": v,
                "pct": round(v / total * 100, 1) if total else 0,
            }
            for k, v in counter.most_common()
        ]
        return {"total_minutes": total, "items": items}

    distribution = {
        "day": distribution_for(is_today),
        "week": distribution_for(is_this_week),
        "month": distribution_for(lambda t: True),
    }

    # ---- hours_24（按北京时间 started_at 的 hour 分桶）----
    hours = [0] * 24
    for t in tasks_30d:
        if t.get("status") != "completed":
            continue
        dt = to_cn(t.get("started_at"))
        if dt is None:
            continue
        hours[dt.hour] += (t.get("default_minutes") or 0)
    hours_24 = [{"hour": h, "minutes": m} for h, m in enumerate(hours)]

    # ---- days_30（按北京时间 completed_at 的日期分桶）----
    day_minutes: dict = defaultdict(int)
    for t in tasks_30d:
        if t.get("status") != "completed":
            continue
        d = cn_date(t, "completed_at")
        if not d:
            continue
        day_minutes[d] += (t.get("default_minutes") or 0)

    days_30 = []
    for i in range(30):
        d = (now - timedelta(days=29 - i)).strftime("%Y-%m-%d")
        days_30.append({"date": d, "minutes": day_minutes.get(d, 0)})

    # ---- cumulative（全部 completed 历史，按北京时间）----
    cum_days: set = set()
    cum_minutes = 0
    for t in tasks_all:
        d = cn_date(t, "completed_at")
        if d:
            cum_days.add(d)
            cum_minutes += (t.get("default_minutes") or 0)

    cumulative = {
        "total_days": len(cum_days),
        "total_minutes": cum_minutes,
    }

    return {
        "today": today_data,
        "distribution": distribution,
        "hours_24": hours_24,
        "days_30": days_30,
        "cumulative": cumulative,
        "today_date": today_str,
    }
