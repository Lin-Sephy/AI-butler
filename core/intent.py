"""DeepSeek 调用 v5：闲聊 / 计划双模式。

v5.0 重构（2026-04-20，见开工文档）：
- call_chat(mode="chat"/"plan")：闲聊纯文本，计划模式注册 function calling 工具
- 闲聊模式无信号块，DS 输出纯文本
- 计划模式 DS 可调 4 个查询工具，输出末尾可能带 ---judgment---{"confirmed": true}
- call_task 保留作为 v4 遗留（api.py 当前还在引用，v5.0 完整切换后才砍）
"""

import json
import logging
import httpx
from openai import OpenAI
import config
from prompts.system_prompt import (
    get_chat_prompt, get_task_prompt,
    build_chat_message, build_task_message,
)
from core.plan_tools import PLAN_MODE_TOOLS, execute_tool

# ---- API 调用参数 ----
API_CONFIG = {
    "model": config.DEEPSEEK_MODEL,
    "temperature": 0.7,
    "max_tokens": 500,
    "top_p": 0.9,
}

# 计划模式 function calling 最多几轮
MAX_TOOL_ROUNDS = 5

# ---- 兜底 ----
FALLBACK_TEMPLATES = {
    5: "你现在状态不错！想做点什么吗？",
    4: "状态还行，想做什么跟我说～",
    3: "今天精力一般，要不先做件简单的事热热身？",
    2: "现在精力比较低，建议先休息一下或者做个最简单的小任务。",
    1: "你现在最需要的是休息。先睡一觉或者出去走走，其他的等恢复了再说。",
}

MID_CHAT_FALLBACK = "网络开小差了，你刚才说的我没接住——能再说一次吗？"

# v4 遗留：部分上层代码仍期望 result 里有 signal 字段。v5 里始终为空 dict，
# 让 should_trigger_task 等老函数拿到 {} 就自然 no-op。
EMPTY_SIGNAL: dict = {}


def _get_client() -> OpenAI:
    """创建 OpenAI 客户端。"""
    return OpenAI(
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL,
        timeout=httpx.Timeout(30.0, connect=10.0),
        max_retries=1,
    )


def _parse_chat_reply(raw: str) -> tuple[str, bool]:
    """从 DS 回复中分离正文和 ---judgment--- 信号块。

    返回 (reply_text, confirmed)。
    闲聊模式 DS 不应该输出 judgment 块，但如果有，忽略即可。
    计划模式仅当 judgment 里 confirmed=true 时 confirmed 返回 True。
    """
    if "---judgment---" not in raw:
        return raw.strip(), False

    reply_part, _, signal_part = raw.partition("---judgment---")
    reply = reply_part.strip()

    signal_text = signal_part.strip()
    if signal_text.startswith("```"):
        signal_text = signal_text.split("\n", 1)[1] if "\n" in signal_text else signal_text[3:]
    if signal_text.endswith("```"):
        signal_text = signal_text[:-3]
    signal_text = signal_text.strip()

    try:
        parsed = json.loads(signal_text)
        confirmed = bool(parsed.get("confirmed"))
    except (json.JSONDecodeError, AttributeError) as e:
        logging.warning(f"[Chat] judgment 块解析失败: {e}")
        confirmed = False

    return reply, confirmed


def call_chat(user_input: str, energy_level: int,
              chat_history: list | None = None,
              user_memo: str = "",
              ai_memo: str = "",
              daily_memo: str = "",
              task_board: str = "",
              session_summary: str = "",
              is_cross_day: bool = False,
              companion_name: str = "小白",
              custom_persona: str = "",
              mode: str = "chat",
              user_id: str | None = None) -> dict:
    """聊天调用。

    mode="chat"：闲聊模式，不注册工具，纯文本输出
    mode="plan"：计划模式，注册 4 个查询工具（function calling），
                 DS 可按需调用；输出末尾可能带 judgment 信号块

    plan 模式必须传 user_id（工具执行要用）。

    返回 {"reply": str, "signal": {}, "confirmed": bool}
    （signal 始终空 dict，保留字段名是为了 api.py 老代码不崩；
     confirmed 仅 plan 模式有意义）
    """
    has_history = bool(chat_history)

    if mode == "plan" and not user_id:
        raise ValueError("call_chat(mode='plan') 需要传 user_id")

    if not config.DEEPSEEK_API_KEY:
        fallback = MID_CHAT_FALLBACK if has_history else FALLBACK_TEMPLATES.get(energy_level, "你好呀～")
        return {"reply": fallback, "signal": dict(EMPTY_SIGNAL), "confirmed": False}

    try:
        client = _get_client()
        system_prompt = get_chat_prompt(
            companion_name=companion_name,
            custom_persona=custom_persona,
            mode=mode,
        )
        user_message = build_chat_message(
            user_input, energy_level,
            user_memo=user_memo, ai_memo=ai_memo,
            daily_memo=daily_memo, task_board=task_board,
            session_summary=session_summary,
            is_cross_day=is_cross_day,
        )

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        if chat_history:
            recent = chat_history[-10:] if session_summary else chat_history[-20:]
            for msg in recent:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})

        tools = PLAN_MODE_TOOLS if mode == "plan" else None

        # Function calling 循环：闲聊模式一次就出；计划模式可能调工具再返
        raw_final = ""
        for _ in range(MAX_TOOL_ROUNDS):
            resp = client.chat.completions.create(
                model=API_CONFIG["model"],
                temperature=API_CONFIG["temperature"],
                max_tokens=API_CONFIG["max_tokens"],
                top_p=API_CONFIG["top_p"],
                messages=messages,
                tools=tools,
            )
            msg = resp.choices[0].message
            # 把 assistant 消息回写（OpenAI SDK 对象→dict）
            messages.append(msg.model_dump(exclude_none=True))

            if not msg.tool_calls:
                raw_final = msg.content or ""
                break

            # 依次执行每个工具调用
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    logging.warning(f"[Chat] 工具 {name} 参数 JSON 解析失败: {tc.function.arguments!r}")
                    args = {}
                result = execute_tool(user_id, name, args)
                logging.info(f"[Chat] tool={name} args={args} → {result[:120]}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
        else:
            logging.warning(f"[Chat] function calling 超过 {MAX_TOOL_ROUNDS} 轮未收敛")

        logging.warning(f"[Chat raw] {raw_final[:300]}")
        reply, confirmed = _parse_chat_reply(raw_final)
        if not reply:
            reply = FALLBACK_TEMPLATES.get(energy_level, "你好呀～")

        return {"reply": reply, "signal": dict(EMPTY_SIGNAL), "confirmed": confirmed}

    except Exception as e:
        logging.error(f"[Chat] API 调用失败: {type(e).__name__}: {e}")
        fallback = MID_CHAT_FALLBACK if has_history else FALLBACK_TEMPLATES.get(energy_level, "你好呀～")
        return {"reply": fallback, "signal": dict(EMPTY_SIGNAL), "confirmed": False}


# ════════════════════════════════════════════════════════════
# call_task：v4 遗留，v5.0 切换完成后和 app.py 一起清理
# ════════════════════════════════════════════════════════════


def _parse_task_response(raw: str) -> dict | None:
    """解析任务推荐的 JSON 响应。"""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _validate_task_fields(data: dict) -> dict:
    """校验任务 JSON 字段。"""
    if not isinstance(data.get("task_keyword"), str) or not data["task_keyword"].strip():
        data["task_keyword"] = None

    if data.get("task_type") not in ("work", "rest"):
        data["task_type"] = "work"

    if data.get("suggested_minutes") is not None:
        try:
            val = int(data["suggested_minutes"])
            data["suggested_minutes"] = max(5, min(120, val))
        except (TypeError, ValueError):
            data["suggested_minutes"] = 25

    if data.get("scheduled_at") is not None:
        try:
            from datetime import datetime
            datetime.strptime(data["scheduled_at"], "%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            data["scheduled_at"] = None

    if data.get("scheduled_at") is None:
        data["scheduled_keyword"] = None
    elif not isinstance(data.get("scheduled_keyword"), str) or not data.get("scheduled_keyword", "").strip():
        data["scheduled_keyword"] = None
        data["scheduled_at"] = None

    if not isinstance(data.get("reply"), str) or not data["reply"].strip():
        data["reply"] = None

    return data


def call_task(user_input: str, energy_level: int,
              chat_history: list | None = None,
              completed_tasks: list[str] | None = None,
              context: str = "",
              companion_name: str = "小白",
              custom_persona: str = "") -> dict:
    """任务推荐调用：给出具体任务建议（v4 遗留）。

    v5.0 的计划模式不走这条路径——结构化提取走独立流程。
    保留此函数是因为 api.py 的 /api/chat 仍在 if trigger 分支里引用。
    随着 api.py 在 Step 3 改造完成，此函数可删。
    """
    if not config.DEEPSEEK_API_KEY:
        return {
            "task_keyword": None,
            "suggested_minutes": None,
            "task_type": None,
            "scheduled_at": None,
            "scheduled_keyword": None,
            "reply": FALLBACK_TEMPLATES.get(energy_level, "你好呀～"),
        }

    try:
        client = _get_client()
        system_prompt = get_task_prompt(companion_name=companion_name, custom_persona=custom_persona)
        user_message = build_task_message(
            user_input, energy_level,
            context=context,
            completed_tasks=completed_tasks,
        )

        messages = [{"role": "system", "content": system_prompt}]
        if chat_history:
            recent = chat_history[-10:]
            for msg in recent:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})

        resp = client.chat.completions.create(
            model=API_CONFIG["model"],
            temperature=API_CONFIG["temperature"],
            max_tokens=API_CONFIG["max_tokens"],
            top_p=API_CONFIG["top_p"],
            messages=messages,
        )

        raw = resp.choices[0].message.content
        logging.warning(f"[Task raw] {raw[:300]}")

        parsed = _parse_task_response(raw)
        if parsed is None:
            logging.warning("[Task] JSON 解析失败，使用兜底")
            return {
                "task_keyword": None,
                "reply": raw.strip() or FALLBACK_TEMPLATES.get(energy_level, "你好呀～"),
            }

        parsed = _validate_task_fields(parsed)

        if parsed["reply"] is None:
            parsed["reply"] = FALLBACK_TEMPLATES.get(energy_level, "你好呀～")

        return parsed

    except Exception as e:
        logging.error(f"[Task] API 调用失败: {type(e).__name__}: {e}")
        return {
            "task_keyword": None,
            "suggested_minutes": None,
            "task_type": None,
            "scheduled_at": None,
            "scheduled_keyword": None,
            "reply": MID_CHAT_FALLBACK,
        }
