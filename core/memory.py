"""AI 记忆系统 v2：两级印象（初步/深入）+ 每日快照。

核心机制：
- 初步印象：首次观察到就记录，不传给聊天 DS
- 深入印象：触发 3 次以上且跨 2 天，才升级并传给 DS
- 衰减：初步 7 天过期删除，深入 14 天未触发降级（高频 30 天）
- 矛盾检测：DS 在提取时判断已有印象是否被推翻
"""

import json
import logging
import re
from datetime import timedelta, datetime
import httpx
from openai import OpenAI
import config
from db.database import (
    get_ai_memo, save_ai_memo,
    get_daily_memo, save_daily_memo, now_cn,
)

# ---- 印象系统参数 ----

CONFIRM_THRESHOLD = 3       # 触发次数 >= 3 才升级
CONFIRM_MIN_DAYS = 2        # 跨天数 >= 2 才升级
DRAFT_EXPIRE_DAYS = 7       # 初步印象 7 天没触发就删
CONFIRMED_DECAY_DAYS = 14   # 深入印象 14 天没触发就降级
HIGH_FREQ_THRESHOLD = 10    # 触发 10 次以上，衰减期延长
HIGH_FREQ_DECAY_DAYS = 30

# ---- 提取 Prompt ----

EXTRACT_PROMPT = """你是一个观察者。从对话中提取你对用户的印象，并判断已有印象是否被强化或推翻。同时生成一份对话摘要。

已有印象：
{existing_impressions}

上一轮对话摘要：
{previous_summary}

返回 JSON，不要包含其他内容：
{{
  "reinforced": [0, 2],
  "contradicted": [{{"index": 1, "reason": "原因"}}],
  "new_impressions": ["新的观察印象"],
  "daily": {{
    "emotion": {{"value": "情绪", "source": "原因"}} 或 null,
    "current_task": "在做的事" 或 null
  }},
  "session_summary": "用2-3句话概括当前对话的整体状态：聊了什么话题、用户情绪和意图、有什么待办或决定。要涵盖之前的摘要内容，不要丢失旧信息"
}}

规则：
- 印象是对用户行为模式、性格特点、状态趋势的观察判断，不是事件记录
- 不记录日常琐碎（天气、无意义闲聊）
- 不记录单次事件，除非它揭示了一个模式
- 已有印象被当前对话佐证时放入 reinforced
- 已有印象与当前对话矛盾时放入 contradicted
- 没有新发现时 new_impressions 为空数组
- daily 是当前状态快照：emotion 是此刻情绪，current_task 是当前在做的事
- 如果对话中没有情绪或任务相关信息，daily 对应字段填 null
- session_summary 必须始终填写，即使对话很短"""


# ---- 印象存取 ----

def _get_impressions() -> list[dict]:
    """从 ai_memo 读取印象列表。兼容旧格式（纯文本直接丢弃）。"""
    raw = get_ai_memo()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "impressions" in data:
            return data["impressions"]
        return []
    except json.JSONDecodeError:
        return []


def _save_impressions(impressions: list[dict]) -> None:
    """保存印象列表到 ai_memo。"""
    save_ai_memo(json.dumps({"impressions": impressions}, ensure_ascii=False))


def get_confirmed_impressions_text() -> str:
    """获取深入印象的可读文本，传给聊天 prompt。只返回 confirmed 级别的。"""
    impressions = _get_impressions()
    confirmed = [imp for imp in impressions if imp.get("level") == "confirmed"]
    if not confirmed:
        return ""
    lines = [imp["content"] for imp in confirmed]
    return "背景参考（仅供你内心判断用，不要在对话中直接提及）：\n" + "\n".join(f"- {line}" for line in lines)


def get_impressions_display() -> str:
    """获取印象的展示文本（侧边栏用）。"""
    impressions = _get_impressions()
    if not impressions:
        return ""
    confirmed = [imp for imp in impressions if imp.get("level") == "confirmed"]
    drafts = [imp for imp in impressions if imp.get("level") == "draft"]
    parts = []
    if confirmed:
        for imp in confirmed:
            parts.append(f"✓ {imp['content']}")
    if drafts:
        parts.append(f"（还有 {len(drafts)} 条观察中的印象）")
    return "\n".join(parts)


def _format_existing_impressions(impressions: list[dict]) -> str:
    """格式化已有印象列表传给提取 prompt。"""
    if not impressions:
        return "（暂无已有印象）"
    lines = []
    for i, imp in enumerate(impressions):
        level_tag = "已确认" if imp.get("level") == "confirmed" else "观察中"
        lines.append(f"[{i}] [{level_tag}] {imp['content']}")
    return "\n".join(lines)


# ---- 核心流程 ----

def extract_and_update(chat_history: list, previous_summary: str = "") -> dict:
    """从对话中提取印象 + 更新每日快照 + 生成会话摘要。

    返回 {"updated": bool, "session_summary": str}
    """
    if not config.DEEPSEEK_API_KEY or not chat_history:
        return {"updated": False, "session_summary": previous_summary}

    impressions = _get_impressions()

    recent = chat_history[-20:]
    conv_text = "\n".join(
        f"{'用户' if m['role'] == 'user' else '小白'}: {m['content']}"
        for m in recent if m["role"] in ("user", "assistant")
    )

    try:
        client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            timeout=httpx.Timeout(30.0, connect=10.0),
            max_retries=1,
        )

        prompt = EXTRACT_PROMPT.format(
            existing_impressions=_format_existing_impressions(impressions),
            previous_summary=previous_summary or "（暂无）",
        )

        resp = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            temperature=0.3,
            max_tokens=500,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"对话内容：\n\n{conv_text}"},
            ],
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(raw)

    except Exception as e:
        logging.error(f"[Memory] 提取失败: {type(e).__name__}: {e}")
        return {"updated": False, "session_summary": previous_summary}

    now = now_cn()
    today = now.strftime("%Y-%m-%d")
    now_str = now.strftime("%Y-%m-%d %H:%M")
    updated = False

    # 处理强化
    for idx in result.get("reinforced", []):
        if isinstance(idx, int) and 0 <= idx < len(impressions):
            imp = impressions[idx]
            imp["count"] = imp.get("count", 1) + 1
            if today not in imp.get("trigger_days", []):
                imp.setdefault("trigger_days", []).append(today)
            imp["updated_at"] = now_str
            updated = True

    # 处理推翻
    for item in result.get("contradicted", []):
        idx = item.get("index")
        if isinstance(idx, int) and 0 <= idx < len(impressions):
            imp = impressions[idx]
            if imp.get("level") == "confirmed":
                # 深入印象被推翻 → 降级为初步
                imp["level"] = "draft"
                imp["count"] = max(1, imp.get("count", 1) - 2)
                imp["promoted_at"] = None
                logging.info(f"[Memory] 印象被推翻降级: {imp['content']}，原因: {item.get('reason', '')}")
            else:
                # 初步印象被推翻 → 直接删除
                impressions[idx] = None
                logging.info(f"[Memory] 初步印象被推翻删除: {imp['content']}")
            updated = True

    impressions = [imp for imp in impressions if imp is not None]

    # 处理新印象
    for content in result.get("new_impressions", []):
        if not content or not isinstance(content, str):
            continue
        impressions.append({
            "content": content.strip(),
            "level": "draft",
            "count": 1,
            "trigger_days": [today],
            "created_at": now_str,
            "updated_at": now_str,
            "promoted_at": None,
        })
        updated = True

    # 检查升级条件
    for imp in impressions:
        if imp.get("level") == "draft":
            count = imp.get("count", 1)
            days = len(imp.get("trigger_days", []))
            if count >= CONFIRM_THRESHOLD and days >= CONFIRM_MIN_DAYS:
                imp["level"] = "confirmed"
                imp["promoted_at"] = now_str
                logging.info(f"[Memory] 印象升级为 confirmed: {imp['content']}")
                updated = True

    # 衰减/过期
    impressions = _apply_decay(impressions, now)

    if updated:
        _save_impressions(impressions)

    # 每日快照
    daily = result.get("daily", {})
    if daily:
        _update_daily_memo(daily)
        updated = True

    # 会话摘要
    session_summary = result.get("session_summary", "") or previous_summary

    return {"updated": updated, "session_summary": session_summary}


def _apply_decay(impressions: list[dict], now) -> list[dict]:
    """应用衰减规则，返回清理后的印象列表。"""
    result = []
    for imp in impressions:
        updated_at = imp.get("updated_at")
        if not updated_at:
            continue
        try:
            last_update = datetime.strptime(updated_at, "%Y-%m-%d %H:%M")
            last_update = last_update.replace(tzinfo=now.tzinfo)
            days_since = (now - last_update).days
        except (ValueError, KeyError):
            continue

        if imp.get("level") == "confirmed":
            decay_days = HIGH_FREQ_DECAY_DAYS if imp.get("count", 0) >= HIGH_FREQ_THRESHOLD else CONFIRMED_DECAY_DAYS
            if days_since > decay_days:
                imp["level"] = "draft"
                imp["promoted_at"] = None
                logging.info(f"[Memory] 印象降级为 draft: {imp['content']}")
            result.append(imp)
        else:  # draft
            if days_since <= DRAFT_EXPIRE_DAYS:
                result.append(imp)
            else:
                logging.info(f"[Memory] 初步印象过期删除: {imp['content']}")

    return result


# ---- 每日快照（简化版：只有 emotion + current_task） ----

def _update_daily_memo(daily_data: dict) -> None:
    """覆盖式更新每日快照。"""
    now_str = now_cn().strftime("%Y-%m-%d %H:%M")

    try:
        current = json.loads(get_daily_memo())
    except (json.JSONDecodeError, TypeError):
        current = {}

    if daily_data.get("emotion") and daily_data["emotion"].get("value"):
        current["emotion"] = {
            "value": daily_data["emotion"]["value"],
            "source": daily_data["emotion"].get("source", ""),
            "updated_at": now_str,
        }

    if daily_data.get("current_task"):
        current["current_task"] = {
            "value": daily_data["current_task"],
            "updated_at": now_str,
        }

    save_daily_memo(json.dumps(current, ensure_ascii=False))


def get_filtered_daily_memo() -> str:
    """获取过滤后的每日记忆，返回可读文本。"""
    try:
        current = json.loads(get_daily_memo())
    except (json.JSONDecodeError, TypeError):
        return ""

    if not current:
        return ""

    now = now_cn()
    parts = []

    def _is_recent(item, max_days):
        if not item or not item.get("updated_at"):
            return False
        try:
            updated = datetime.strptime(item["updated_at"], "%Y-%m-%d %H:%M")
            updated = updated.replace(tzinfo=now.tzinfo)
            return (now - updated) <= timedelta(days=max_days)
        except (ValueError, KeyError):
            return False

    # 情绪：2 天过期
    emotion = current.get("emotion")
    if emotion and emotion.get("value") and _is_recent(emotion, 2):
        source = f"（{emotion['source']}）" if emotion.get("source") else ""
        parts.append(f"当前情绪：{emotion['value']}{source}")

    # 当前任务：3 天过期
    task = current.get("current_task")
    if task and task.get("value") and _is_recent(task, 3):
        parts.append(f"在做的事：{task['value']}")

    return "\n".join(parts) if parts else ""


# ---- 关键词匹配（零 API 成本） ----

def bump_on_mention(user_input: str) -> None:
    """用户输入命中已有印象关键词时，更新时间戳+计数。"""
    impressions = _get_impressions()
    if not impressions:
        return

    now = now_cn()
    today = now.strftime("%Y-%m-%d")
    now_str = now.strftime("%Y-%m-%d %H:%M")
    changed = False

    for imp in impressions:
        content = imp.get("content", "")
        if content and any(kw in user_input for kw in _extract_keywords(content)):
            imp["updated_at"] = now_str
            imp["count"] = imp.get("count", 1) + 1
            if today not in imp.get("trigger_days", []):
                imp.setdefault("trigger_days", []).append(today)
            changed = True

    if not changed:
        return

    # 检查升级
    for imp in impressions:
        if imp.get("level") == "draft":
            count = imp.get("count", 1)
            days = len(imp.get("trigger_days", []))
            if count >= CONFIRM_THRESHOLD and days >= CONFIRM_MIN_DAYS:
                imp["level"] = "confirmed"
                imp["promoted_at"] = now_str
                logging.info(f"[Memory] 印象通过关键词匹配升级: {imp['content']}")

    _save_impressions(impressions)
    logging.info("[Memory] 关键词命中，已更新印象计数")


def _extract_keywords(text: str) -> list[str]:
    """从文本中提取 2 字以上的关键词片段用于匹配。"""
    segments = re.split(r'[，。、！？\s,.\-/()（）]+', text)
    return [s for s in segments if len(s) >= 2]


# ---- 兼容旧接口 ----

def update_ai_memory(chat_history: list, previous_summary: str = "") -> dict:
    """入口函数：提取印象 + 每日快照 + 会话摘要。

    返回 {"updated": bool, "session_summary": str}
    """
    return extract_and_update(chat_history, previous_summary=previous_summary)
