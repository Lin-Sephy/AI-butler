"""AI 自动记忆：从对话中提取关键信息，整理并维护记忆库。"""

import json
import logging
import httpx
from openai import OpenAI
import config
from db.database import get_ai_memo, save_ai_memo, get_user_memo

# 记忆整理上限
AI_MEMO_MAX_LINES = 20

EXTRACT_PROMPT = """你是一个记忆提取助手。从以下对话中提取值得长期记住的关键信息。

提取这三类：
1. 用户在做什么项目/任务，以及当前进度
2. 用户的习惯和偏好
3. 用户今天做了什么（完成了哪些任务、进展到哪一步）

规则：
- 不要提取日常琐碎（天气、闲聊）
- 不要提取单次的情绪
- 每条用一句话，包含具体细节
- 如果这段对话确实没有任何有用信息，返回空列表 []

返回 JSON 数组，不要包含其他内容：
["提取的信息1", "提取的信息2"]"""

ORGANIZE_PROMPT = """你是一个记忆整理助手。你会收到两部分内容：
1. 用户手记（用户自己写的背景信息，不能修改或删除）
2. 当前 AI 记忆 + 新提取的信息

请整理 AI 记忆部分，规则：
- 按项目/目标维度组织，不是按天
- 同一个项目的多条进度合并成一行（如"数学做了第1套""数学做了第3套"→"考研数学：已完成真题第1-3套"）
- 删除重复信息
- 删除已过时的信息（如已过去的预定任务）
- 保留用户的习惯偏好
- 如果用户手记里有纠正信息（如"我不是考研是考公"），在 AI 记忆中更新
- 控制在 {max_lines} 行以内
- 每行一条信息，简洁明了

只返回整理后的 AI 记忆内容（纯文本，每行一条），不要包含标题或其他格式。"""


def extract_from_chat(chat_history: list) -> list[str]:
    """从最近的对话中提取关键信息。"""
    if not config.DEEPSEEK_API_KEY or not chat_history:
        return []

    # 只取最近 20 条消息
    recent = chat_history[-20:]
    conv_text = "\n".join(
        f"{'用户' if m['role'] == 'user' else '小管家'}: {m['content']}"
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
        if isinstance(result, list):
            return [str(item) for item in result if item]
        return []
    except Exception as e:
        logging.error(f"[Memory] 提取失败: {type(e).__name__}: {e}")
        return []


def organize_memo(new_items: list[str]) -> str:
    """整理 AI 记忆：合并新信息，去重，控制行数。"""
    current_ai_memo = get_ai_memo()
    user_memo = get_user_memo()

    # 如果没有新信息也没有旧记忆，不需要整理
    if not new_items and not current_ai_memo:
        return ""

    # 拼接当前记忆和新提取的内容
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
        # 确保不超过行数上限
        lines = [line for line in result.split("\n") if line.strip()]
        if len(lines) > AI_MEMO_MAX_LINES:
            lines = lines[:AI_MEMO_MAX_LINES]
        return "\n".join(lines)
    except Exception as e:
        logging.error(f"[Memory] 整理失败: {type(e).__name__}: {e}")
        # 整理失败就直接追加新内容
        if new_items and current_ai_memo:
            lines = current_ai_memo.split("\n") + new_items
            return "\n".join(lines[:AI_MEMO_MAX_LINES])
        return current_ai_memo


def update_ai_memory(chat_history: list) -> bool:
    """完整流程：提取 → 整理 → 保存。返回是否有更新。"""
    new_items = extract_from_chat(chat_history)
    if not new_items and not get_ai_memo():
        return False

    organized = organize_memo(new_items)
    if organized != get_ai_memo():
        save_ai_memo(organized)
        logging.info(f"[Memory] AI 记忆已更新（{len(organized.split(chr(10)))} 行）")
        return True
    return False
