"""AI 记忆系统：长期记忆 + 每日记忆（覆盖式快照）。"""

import json
import logging
from datetime import timedelta
import httpx
from openai import OpenAI
import config
from db.database import (
    get_ai_memo, save_ai_memo, get_user_memo,
    get_daily_memo, save_daily_memo, now_cn,
)

# 长期记忆上限
AI_MEMO_MAX_LINES = 20

# ---- 提取 Prompt ----

EXTRACT_PROMPT = """你是一个记忆提取助手。从以下对话中提取两类信息：

【长期记忆】值得长期记住的：
- 用户在做什么项目/任务
- 用户的习惯和偏好
- 用户的身份背景

【每日记忆】当前状态快照：
- emotion: 用户现在的情绪（开心/烦躁/焦虑/平静/疲惫等），以及原因
- energy_impression: 你感知到的用户精力水平（1-5），信息不够填 null
- current_task: 用户现在在做或打算做的事
- recent_events: 近期发生的具体事件（如"导师催了进度""刚跑完步"）

规则：
- 不要提取日常琐碎（天气、无意义闲聊）
- 每日记忆是覆盖式的：如果有新情绪就替换旧情绪，有新任务就替换旧任务
- 如果这段对话没有新信息，对应字段填 null

返回 JSON，不要包含其他内容：
{
  "long_term": ["长期信息1", "长期信息2"],
  "daily": {
    "emotion": {"value": "情绪", "source": "原因"} 或 null,
    "energy_impression": 数字或null,
    "current_task": "在做的事" 或 null,
    "recent_events": [{"content": "事件描述"}] 或 []
  }
}"""

ORGANIZE_PROMPT = """你是一个记忆整理助手。你会收到两部分内容：
1. 用户手记（用户自己写的背景信息，不能修改或删除）
2. 当前 AI 记忆 + 新提取的信息

请整理 AI 记忆部分，规则：
- 按项目/目标维度组织，不是按天
- 同一个项目的多条进度合并成一行
- 删除重复信息
- 删除已过时的信息
- 保留用户的习惯偏好
- 如果用户手记里有纠正信息，在 AI 记忆中更新
- 控制在 {max_lines} 行以内
- 每行一条信息，简洁明了

只返回整理后的 AI 记忆内容（纯文本，每行一条），不要包含标题或其他格式。"""


def extract_from_chat(chat_history: list) -> dict:
    """从最近的对话中提取长期记忆和每日记忆。"""
    if not config.DEEPSEEK_API_KEY or not chat_history:
        return {"long_term": [], "daily": {}}

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
        resp = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            temperature=0.3,
            max_tokens=500,
            messages=[
                {"role": "system", "content": EXTRACT_PROMPT},
                {"role": "user", "content": f"对话内容：\n\n{conv_text}"},
            ],
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(raw)

        # 兼容旧格式（纯数组）
        if isinstance(result, list):
            return {"long_term": [str(item) for item in result if item], "daily": {}}

        return {
            "long_term": [str(item) for item in result.get("long_term", []) if item],
            "daily": result.get("daily", {}),
        }
    except Exception as e:
        logging.error(f"[Memory] 提取失败: {type(e).__name__}: {e}")
        return {"long_term": [], "daily": {}}


def organize_memo(new_items: list[str]) -> str:
    """整理长期记忆：合并新信息，去重，控制行数。"""
    current_ai_memo = get_ai_memo()
    user_memo = get_user_memo()

    if not new_items and not current_ai_memo:
        return ""

    memo_parts = []
    if current_ai_memo.strip():
        memo_parts.append(f"当前 AI 记忆：\n{current_ai_memo}")
    if new_items:
        memo_parts.append(f"新提取的信息：\n" + "\n".join(f"- {item}" for item in new_items))

    if not memo_parts:
        return current_ai_memo

    try:
        client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            timeout=httpx.Timeout(30.0, connect=10.0),
            max_retries=1,
        )

        user_memo_section = f"用户手记：\n{user_memo}" if user_memo.strip() else "用户手记：（空）"

        resp = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            temperature=0.3,
            max_tokens=800,
            messages=[
                {"role": "system", "content": ORGANIZE_PROMPT.format(max_lines=AI_MEMO_MAX_LINES)},
                {"role": "user", "content": f"{user_memo_section}\n\n{chr(10).join(memo_parts)}"},
            ],
        )
        result = resp.choices[0].message.content.strip()
        lines = [line for line in result.split("\n") if line.strip()]
        if len(lines) > AI_MEMO_MAX_LINES:
            lines = lines[:AI_MEMO_MAX_LINES]
        return "\n".join(lines)
    except Exception as e:
        logging.error(f"[Memory] 整理失败: {type(e).__name__}: {e}")
        if new_items and current_ai_memo:
            lines = current_ai_memo.split("\n") + new_items
            return "\n".join(lines[:AI_MEMO_MAX_LINES])
        return current_ai_memo


def update_daily_memo(daily_data: dict) -> None:
    """覆盖式更新每日记忆快照。新值替换旧值，null 值保留旧值。"""
    now = now_cn()
    now_str = now.strftime("%Y-%m-%d %H:%M")

    try:
        current = json.loads(get_daily_memo())
    except (json.JSONDecodeError, TypeError):
        current = {}

    # 更新情绪（新情绪覆盖旧情绪）
    if daily_data.get("emotion") and daily_data["emotion"].get("value"):
        old_emotion = current.get("emotion", {}).get("value", "")
        is_same = daily_data["emotion"]["value"] == old_emotion
        current["emotion"] = {
            "value": daily_data["emotion"]["value"],
            "source": daily_data["emotion"].get("source", ""),
            "updated_at": now_str,
            "mention_count": current.get("emotion", {}).get("mention_count", 0) + 1 if is_same else 1,
        }

    # 更新精力印象
    if daily_data.get("energy_impression") is not None:
        current["energy_impression"] = {
            "value": daily_data["energy_impression"],
            "updated_at": now_str,
        }

    # 更新当前任务
    if daily_data.get("current_task"):
        old_task = current.get("current_task", {}).get("value", "")
        # 简单判断是否同一件事（包含关系）
        new_task = daily_data["current_task"]
        is_same = old_task and (old_task in new_task or new_task in old_task)
        current["current_task"] = {
            "value": new_task,
            "updated_at": now_str,
            "mention_count": current.get("current_task", {}).get("mention_count", 0) + 1 if is_same else 1,
        }

    # 更新近期事件（追加，但去重；重复提及的更新时间戳+计数）
    if daily_data.get("recent_events"):
        existing_events = current.get("recent_events", [])
        existing_map = {e.get("content", ""): i for i, e in enumerate(existing_events)}
        for event in daily_data["recent_events"]:
            content = event.get("content", "")
            if not content:
                continue
            # 检查是否已有相似事件（包含关系匹配）
            matched_idx = None
            for existing_content, idx in existing_map.items():
                if existing_content in content or content in existing_content:
                    matched_idx = idx
                    break
            if matched_idx is not None:
                existing_events[matched_idx]["updated_at"] = now_str
                existing_events[matched_idx]["mention_count"] = existing_events[matched_idx].get("mention_count", 1) + 1
            else:
                existing_events.append({
                    "content": content,
                    "updated_at": now_str,
                    "mention_count": 1,
                })
                existing_map[content] = len(existing_events) - 1
        current["recent_events"] = existing_events

    save_daily_memo(json.dumps(current, ensure_ascii=False))


def get_filtered_daily_memo() -> str:
    """获取过滤后的每日记忆（过期项已移除），返回可读文本。"""
    try:
        current = json.loads(get_daily_memo())
    except (json.JSONDecodeError, TypeError):
        return ""

    if not current:
        return ""

    now = now_cn()
    parts = []

    from datetime import datetime

    def _is_valid(item, base_days):
        if not item or not item.get("updated_at"):
            return False
        try:
            updated = datetime.strptime(item["updated_at"], "%Y-%m-%d %H:%M")
            updated = updated.replace(tzinfo=now.tzinfo)
            max_days = _get_expiry_days(base_days, item.get("mention_count", 1))
            return (now - updated) <= timedelta(days=max_days)
        except (ValueError, KeyError):
            return False

    # 情绪：基础 2 天，高频提及翻倍
    emotion = current.get("emotion")
    if emotion and emotion.get("value") and _is_valid(emotion, 2):
        source = f"（{emotion['source']}）" if emotion.get("source") else ""
        mention = f"[提及{emotion['mention_count']}次]" if emotion.get("mention_count", 1) >= 3 else ""
        parts.append(f"当前情绪：{emotion['value']}{source}{mention}")

    # 精力印象：基础 1 天
    energy = current.get("energy_impression")
    if energy and energy.get("value") is not None and _is_valid(energy, 1):
        parts.append(f"精力印象：{energy['value']}档")

    # 当前任务：基础 3 天，高频提及翻倍
    task = current.get("current_task")
    if task and task.get("value") and _is_valid(task, 3):
        mention = f"[提及{task['mention_count']}次]" if task.get("mention_count", 1) >= 3 else ""
        parts.append(f"在做的事：{task['value']}{mention}")

    # 近期事件：基础 2 天，高频提及翻倍
    events = current.get("recent_events", [])
    valid_events = []
    for event in events:
        if _is_valid(event, 2):
            mention = f"[提及{event['mention_count']}次]" if event.get("mention_count", 1) >= 3 else ""
            valid_events.append(f"{event['content']}{mention}")
    if valid_events:
        parts.append(f"近期事件：{'、'.join(valid_events)}")

    # 同时清理过期数据，写回数据库
    _cleanup_expired(current, now)

    return "\n".join(parts) if parts else ""


def _get_expiry_days(base_days: int, mention_count: int) -> int:
    """根据提及次数延长过期天数。提及 3 次以上翻倍。"""
    if mention_count >= 3:
        return base_days * 2
    return base_days


def _cleanup_expired(memo: dict, now) -> None:
    """清理过期的每日记忆条目。提及次数高的延长保留。"""
    from datetime import datetime
    changed = False

    base_expiry = {"emotion": 2, "energy_impression": 1, "current_task": 3}
    for key, base_days in base_expiry.items():
        item = memo.get(key)
        if item and item.get("updated_at"):
            try:
                updated = datetime.strptime(item["updated_at"], "%Y-%m-%d %H:%M")
                updated = updated.replace(tzinfo=now.tzinfo)
                max_days = _get_expiry_days(base_days, item.get("mention_count", 1))
                if (now - updated) > timedelta(days=max_days):
                    del memo[key]
                    changed = True
            except (ValueError, KeyError):
                pass

    events = memo.get("recent_events", [])
    valid = []
    for event in events:
        try:
            updated = datetime.strptime(event["updated_at"], "%Y-%m-%d %H:%M")
            updated = updated.replace(tzinfo=now.tzinfo)
            max_days = _get_expiry_days(2, event.get("mention_count", 1))
            if (now - updated) <= timedelta(days=max_days):
                valid.append(event)
        except (ValueError, KeyError):
            pass
    if len(valid) != len(events):
        memo["recent_events"] = valid
        changed = True

    if changed:
        save_daily_memo(json.dumps(memo, ensure_ascii=False))


def bump_on_mention(user_input: str) -> None:
    """每轮对话后调用：用户输入命中已有记忆关键词时，更新时间戳+计数。零 API 成本。"""
    try:
        current = json.loads(get_daily_memo())
    except (json.JSONDecodeError, TypeError):
        return

    if not current:
        return

    now_str = now_cn().strftime("%Y-%m-%d %H:%M")
    changed = False

    # 匹配情绪关键词
    emotion = current.get("emotion")
    if emotion and emotion.get("source"):
        # 用 source 里的关键词匹配（如"导师催"→ 用户输入包含"导师"）
        source_keywords = [w for w in emotion["source"] if len(w) >= 2]
        if any(kw in user_input for kw in _extract_keywords(emotion["source"])):
            emotion["updated_at"] = now_str
            emotion["mention_count"] = emotion.get("mention_count", 1) + 1
            changed = True

    # 匹配当前任务
    task = current.get("current_task")
    if task and task.get("value"):
        if any(kw in user_input for kw in _extract_keywords(task["value"])):
            task["updated_at"] = now_str
            task["mention_count"] = task.get("mention_count", 1) + 1
            changed = True

    # 匹配近期事件
    for event in current.get("recent_events", []):
        content = event.get("content", "")
        if content and any(kw in user_input for kw in _extract_keywords(content)):
            event["updated_at"] = now_str
            event["mention_count"] = event.get("mention_count", 1) + 1
            changed = True

    if changed:
        save_daily_memo(json.dumps(current, ensure_ascii=False))
        logging.info(f"[Memory] 关键词命中，已更新提及计数")


def _extract_keywords(text: str) -> list[str]:
    """从文本中提取 2 字以上的关键词片段用于匹配。"""
    # 简单策略：按常见分隔符切分，保留 2 字以上的片段
    import re
    segments = re.split(r'[，。、！？\s,.\-/()（）]+', text)
    return [s for s in segments if len(s) >= 2]


def update_ai_memory(chat_history: list) -> bool:
    """完整流程：提取 → 长期记忆整理 + 每日记忆更新。返回是否有更新。"""
    extracted = extract_from_chat(chat_history)
    updated = False

    # 长期记忆
    long_term = extracted.get("long_term", [])
    if long_term or get_ai_memo():
        organized = organize_memo(long_term)
        if organized != get_ai_memo():
            save_ai_memo(organized)
            logging.info(f"[Memory] 长期记忆已更新（{len(organized.split(chr(10)))} 行）")
            updated = True

    # 每日记忆
    daily = extracted.get("daily", {})
    if daily:
        update_daily_memo(daily)
        logging.info("[Memory] 每日记忆已更新")
        updated = True

    return updated
