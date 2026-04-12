"""DeepSeek 调用 v4：聊天 + 任务分离架构。

- call_chat()：自然聊天 + 输出观察信号，每轮都调用
- call_task()：给出具体任务建议，仅 Python 判断需要时调用
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

# ---- API 调用参数 ----
API_CONFIG = {
    "model": config.DEEPSEEK_MODEL,
    "temperature": 0.7,
    "max_tokens": 500,
    "top_p": 0.9,
}

# ---- 兜底 ----
FALLBACK_TEMPLATES = {
    5: "你现在状态不错！想做点什么吗？",
    4: "状态还行，想做什么跟我说～",
    3: "今天精力一般，要不先做件简单的事热热身？",
    2: "现在精力比较低，建议先休息一下或者做个最简单的小任务。",
    1: "你现在最需要的是休息。先睡一觉或者出去走走，其他的等恢复了再说。",
}

MID_CHAT_FALLBACK = "网络开小差了，你刚才说的我没接住——能再说一次吗？"

EMPTY_SIGNAL = {
    "energy_impression": None,
    "emotion": None,
    "mentioned_activity": None,
    "activity_category": None,
    "user_attitude": None,
    "scheduled_time": None,
}


def _get_client() -> OpenAI:
    """创建 OpenAI 客户端。"""
    return OpenAI(
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL,
        timeout=httpx.Timeout(30.0, connect=10.0),
        max_retries=1,
    )


def _parse_chat_response(raw: str) -> dict:
    """解析聊天响应：纯文本回复 + 信号块。

    格式：
        聊天回复文本

        ---signal---
        {"energy_impression": ..., ...}
    """
    signal = dict(EMPTY_SIGNAL)
    reply = raw.strip()

    if "---signal---" in raw:
        parts = raw.split("---signal---", 1)
        reply = parts[0].strip()
        try:
            signal_text = parts[1].strip()
            # 去掉可能的 markdown 代码块标记
            if signal_text.startswith("```"):
                signal_text = signal_text.split("\n", 1)[1] if "\n" in signal_text else signal_text[3:]
            if signal_text.endswith("```"):
                signal_text = signal_text[:-3]
            signal_text = signal_text.strip()
            parsed = json.loads(signal_text)
            # 只取已知字段
            for key in EMPTY_SIGNAL:
                if key in parsed and parsed[key] is not None:
                    signal[key] = parsed[key]
        except (json.JSONDecodeError, IndexError) as e:
            logging.warning(f"[Chat] 信号解析失败: {e}")

    # 验证 energy_impression
    if signal["energy_impression"] is not None:
        try:
            val = int(signal["energy_impression"])
            signal["energy_impression"] = max(1, min(5, val))
        except (TypeError, ValueError):
            signal["energy_impression"] = None

    # 验证 activity_category
    if signal["activity_category"] not in ("work", "rest", "life", None):
        signal["activity_category"] = None

    # 验证 user_attitude
    if signal["user_attitude"] not in ("wants_help", "wants_to_start", "just_sharing", "frustrated", None):
        signal["user_attitude"] = None

    return {"reply": reply, "signal": signal}


def call_chat(user_input: str, energy_level: int,
              chat_history: list | None = None,
              persona: str = "infp",
              user_memo: str = "",
              ai_memo: str = "",
              daily_memo: str = "",
              task_board: str = "",
              session_summary: str = "",
              is_cross_day: bool = False,
              companion_name: str = "小白",
              custom_persona: str = "") -> dict:
    """聊天调用：自然聊天 + 输出观察信号。

    有 session_summary 时用"摘要 + 最近 5 条"，否则用"最近 20 条"。
    返回 {"reply": str, "signal": dict}
    """
    has_history = bool(chat_history)

    if not config.DEEPSEEK_API_KEY:
        fallback = MID_CHAT_FALLBACK if has_history else FALLBACK_TEMPLATES.get(energy_level, "你好呀～")
        return {"reply": fallback, "signal": dict(EMPTY_SIGNAL)}

    try:
        client = _get_client()
        system_prompt = get_chat_prompt(persona, companion_name=companion_name, custom_persona=custom_persona)
        user_message = build_chat_message(
            user_input, energy_level,
            user_memo=user_memo, ai_memo=ai_memo,
            daily_memo=daily_memo, task_board=task_board,
            session_summary=session_summary,
            is_cross_day=is_cross_day,
        )

        messages = [{"role": "system", "content": system_prompt}]
        if chat_history:
            if session_summary:
                # 有摘要：传最近 10 条（5 轮），摘要覆盖更早的上下文
                recent = chat_history[-10:]
            else:
                recent = chat_history[-20:]
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
        logging.warning(f"[Chat raw] {raw[:300]}")

        result = _parse_chat_response(raw)

        if not result["reply"]:
            result["reply"] = FALLBACK_TEMPLATES.get(energy_level, "你好呀～")

        return result

    except Exception as e:
        logging.error(f"[Chat] API 调用失败: {type(e).__name__}: {e}")
        fallback = MID_CHAT_FALLBACK if has_history else FALLBACK_TEMPLATES.get(energy_level, "你好呀～")
        return {"reply": fallback, "signal": dict(EMPTY_SIGNAL)}


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
              persona: str = "infp",
              completed_tasks: list[str] | None = None,
              context: str = "",
              companion_name: str = "小白",
              custom_persona: str = "") -> dict:
    """任务推荐调用：给出具体任务建议。

    仅在 Python 判断需要推任务时调用。
    返回包含 task_keyword/suggested_minutes/task_type/reply 等字段的 dict。
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
        system_prompt = get_task_prompt(persona, companion_name=companion_name, custom_persona=custom_persona)
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
