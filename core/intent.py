"""DeepSeek 单次调用：意图判断 + 回复生成（v2 架构）。"""

import json
import httpx
from openai import OpenAI
import config
from prompts.system_prompt import get_system_prompt, build_user_message

# ---- API 调用参数 ----
API_CONFIG = {
    "model": config.DEEPSEEK_MODEL,
    "temperature": 0.7,
    "max_tokens": 500,
    "top_p": 0.9,
}

# ---- API 完全不可用时的兜底 ----
FALLBACK_TEMPLATES = {
    5: "你现在状态不错！想做点什么吗？",
    4: "状态还行，想做什么跟我说～",
    3: "今天精力一般，要不先做件简单的事热热身？",
    2: "现在精力比较低，建议先休息一下或者做个最简单的小任务。",
    1: "你现在最需要的是休息。先睡一觉或者出去走走，其他的等恢复了再说。",
}


MID_CHAT_FALLBACK = "网络开小差了，你刚才说的我没接住——能再说一次吗？"


def _default_response(energy_level: int, has_history: bool = False) -> dict:
    """API 完全失败时的兜底响应。

    has_history=True 时说明是对话中途超时，用承接性回复而非冷启动模板。
    """
    if has_history:
        reply = MID_CHAT_FALLBACK
    else:
        reply = FALLBACK_TEMPLATES.get(energy_level, "你好呀，今天想做点什么？")

    return {
        "willingness": "unclear",
        "status": "blocked" if energy_level <= 2 else "ready",
        "combo": "F" if energy_level <= 2 else "C",
        "state_tags": [],
        "task_keyword": None,
        "resistance_source": "none",
        "suggested_energy": None,
        "reply": reply,
    }


def parse_ai_response(raw_text: str) -> dict | None:
    """解析 AI 返回的 JSON，带容错。"""
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _validate_fields(data: dict) -> dict:
    """校验并修正字段值。"""
    valid_willingness = {"want", "resist", "unclear"}
    valid_status = {"ready", "blocked"}
    valid_combos = {"A", "B", "C", "D", "E", "F"}
    valid_sources = {"body_signal", "env_stuffy", "mental_stuck", "want_play", "none"}

    if data.get("willingness") not in valid_willingness:
        data["willingness"] = "unclear"
    if data.get("status") not in valid_status:
        data["status"] = "ready"
    if data.get("combo") not in valid_combos:
        # 根据 willingness + status 推导 combo
        combo_map = {
            ("want", "ready"): "A", ("resist", "ready"): "B", ("unclear", "ready"): "C",
            ("want", "blocked"): "D", ("resist", "blocked"): "E", ("unclear", "blocked"): "F",
        }
        data["combo"] = combo_map.get((data["willingness"], data["status"]), "C")
    if not isinstance(data.get("state_tags"), list):
        data["state_tags"] = []
    if data.get("resistance_source") not in valid_sources:
        data["resistance_source"] = "none"
    if data.get("suggested_energy") is not None:
        try:
            val = int(data["suggested_energy"])
            data["suggested_energy"] = max(1, min(5, val))
        except (TypeError, ValueError):
            data["suggested_energy"] = None
    if data.get("task_type") not in ("work", "rest", None):
        data["task_type"] = "work"

    if data.get("suggested_minutes") is not None:
        try:
            val = int(data["suggested_minutes"])
            data["suggested_minutes"] = max(5, min(120, val))
        except (TypeError, ValueError):
            data["suggested_minutes"] = None

    if not isinstance(data.get("reply"), str) or not data["reply"].strip():
        data["reply"] = None  # 由调用方兜底

    return data


def call_ai(user_input: str, energy_level: int,
            chat_history: list | None = None, persona: str = "gentle") -> dict:
    """调用 DeepSeek 完成意图判断 + 回复生成。

    chat_history: 最近的聊天记录列表，每项为 {"role": "user"|"assistant", "content": str}。
    返回包含 willingness/status/combo/reply 等字段的 dict。
    API 失败时返回兜底响应。
    """
    has_history = bool(chat_history)

    if not config.DEEPSEEK_API_KEY:
        return _default_response(energy_level, has_history)

    try:
        client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            timeout=httpx.Timeout(15.0, connect=5.0),
            max_retries=1,
        )

        system_prompt = get_system_prompt(persona)
        user_message = build_user_message(user_input, energy_level)

        # 构造消息：system + 最近聊天历史 + 当前输入
        messages = [{"role": "system", "content": system_prompt}]
        if chat_history:
            # 最多带最近 10 轮（20 条消息）
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
        import logging
        logging.warning(f"[DeepSeek raw] {raw[:300]}")

        parsed = parse_ai_response(raw)

        if parsed is None:
            logging.warning("[DeepSeek] JSON parse failed, using fallback")
            return _default_response(energy_level, has_history)

        parsed = _validate_fields(parsed)
        logging.warning(f"[DeepSeek] combo={parsed.get('combo')} reply={str(parsed.get('reply'))[:80]}")

        # reply 为空时用兜底模板
        if parsed["reply"] is None:
            logging.warning("[DeepSeek] reply is None, using fallback template")
            parsed["reply"] = FALLBACK_TEMPLATES.get(energy_level, "你好呀，今天想做点什么？")

        return parsed

    except Exception as e:
        import logging
        logging.error(f"DeepSeek API call failed: {type(e).__name__}: {e}")
        return _default_response(energy_level, has_history)
