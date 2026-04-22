"""DeepSeek 调用 v5：闲聊 / 计划双模式。

v5.0 重构（2026-04-20，见开工文档）：
- call_chat(mode="chat"/"plan")：闲聊纯文本，计划模式注册 function calling 工具
- 闲聊模式无信号块，DS 输出纯文本
- 计划模式 DS 可调查询/写入工具，输出末尾可能带 ---judgment---{"confirmed": true}
- v4 的 call_task / EMPTY_SIGNAL / TASK prompt 全套已在 v5 迁移完成后清理（2026-04-22）
"""

import json
import logging
import httpx
from openai import OpenAI
import config
from prompts.system_prompt import get_chat_prompt, build_chat_message
from core.plan_tools import PLAN_MODE_TOOLS, execute_tool

# ---- API 调用参数 ----
API_CONFIG = {
    "model": config.DEEPSEEK_MODEL,
    "temperature": 0.7,
    "max_tokens": 500,
    "top_p": 0.9,
}

# 计划模式 function calling 最多几轮
# 一次调整计划可能需要：query_tasks (1) + 多条 delete_task (N) + 最终回复 (1)
# DS 不并发调工具，每条 delete 算一轮，所以要留足余量。15 够常规场景用了
MAX_TOOL_ROUNDS = 15

# ---- 兜底 ----
# v5 不再按精力档位分兜底文案——精力系统已砍
FRESH_FALLBACK = "你好呀～今天过得怎么样？"
MID_CHAT_FALLBACK = "网络开小差了，你刚才说的我没接住——能再说一次吗？"


def _get_client(user_llm: dict | None = None) -> tuple[OpenAI, str]:
    """创建 OpenAI 客户端。

    如果 user_llm 里有完整的 base_url/api_key/model，走用户自带（BYOK）；
    否则回退默认 DeepSeek。

    返回 (client, model)——model 名字每个 provider 不同，所以跟 client 一起返。
    """
    if user_llm and user_llm.get("base_url") and user_llm.get("api_key") and user_llm.get("model"):
        return OpenAI(
            api_key=user_llm["api_key"],
            base_url=user_llm["base_url"],
            timeout=httpx.Timeout(60.0, connect=10.0),
            max_retries=1,
        ), user_llm["model"]

    return OpenAI(
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL,
        timeout=httpx.Timeout(60.0, connect=10.0),
        max_retries=1,
    ), API_CONFIG["model"]


def _parse_chat_reply(raw: str, mode: str = "chat") -> tuple[str, bool]:
    """从 DS 回复中分离正文和 ---judgment--- 信号块。

    返回 (reply_text, confirmed)。
    闲聊模式 DS 不应输出 judgment 块；如果 DS 违规输出，整体当正文保留、confirmed=False
    （不承认 v4-like 的隐式触发）。计划模式按正常解析。
    """
    if "---judgment---" not in raw:
        return raw.strip(), False

    if mode != "plan":
        # 闲聊模式不承认 judgment 块，整体当文本——保留完整输出避免截断
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


def call_chat(user_input: str,
              chat_history: list | None = None,
              user_memo: str = "",
              ai_memo: str = "",
              daily_memo: str = "",
              task_board: str = "",
              companion_name: str = "小白",
              custom_persona: str = "",
              mode: str = "chat",
              user_id: str | None = None,
              user_llm: dict | None = None) -> dict:
    """聊天调用。

    mode="chat"：闲聊模式，不注册工具，纯文本输出
    mode="plan"：计划模式，注册 function calling 工具（查询 + 写入），
                 DS 可按需调用；输出末尾可能带 judgment 信号块（confirmed）

    plan 模式必须传 user_id（工具执行要用）。

    user_llm：BYOK 用户配置（provider/base_url/model/api_key）。
              完整时走用户的，否则回退默认 DeepSeek。

    返回 {"reply": str, "confirmed": bool, "created_tasks": list}
    """
    has_history = bool(chat_history)

    if mode == "plan" and not user_id:
        raise ValueError("call_chat(mode='plan') 需要传 user_id")

    # 有用户自带 key 就绕过默认 key 的判断
    has_user_key = bool(user_llm and user_llm.get("api_key") and user_llm.get("base_url") and user_llm.get("model"))
    if not has_user_key and not config.DEEPSEEK_API_KEY:
        fallback = MID_CHAT_FALLBACK if has_history else FRESH_FALLBACK
        return {"reply": fallback, "confirmed": False}

    try:
        client, model_name = _get_client(user_llm)
        system_prompt = get_chat_prompt(
            companion_name=companion_name,
            custom_persona=custom_persona,
            mode=mode,
        )
        user_message = build_chat_message(
            user_input,
            user_memo=user_memo, ai_memo=ai_memo,
            daily_memo=daily_memo, task_board=task_board,
        )

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        if chat_history:
            recent = chat_history[-20:]
            for msg in recent:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})

        tools = PLAN_MODE_TOOLS if mode == "plan" else None
        logging.warning(f"[Chat] mode={mode} tools={'on' if tools else 'off'} user_msg={user_input[:60]!r}")

        # Function calling 循环：闲聊模式一次就出；计划模式可能调工具再返
        raw_final = ""
        created_tasks: list[dict] = []   # 本轮 create_tasks 工具写入的任务（返给前端弹窗）
        for _ in range(MAX_TOOL_ROUNDS):
            resp = client.chat.completions.create(
                model=model_name,
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
                logging.warning(f"[Chat] tool={name} args={args} → {result[:120]}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
                # 收集 create_tasks 的创建结果供前端弹窗用
                if name == "create_tasks":
                    try:
                        parsed = json.loads(result)
                        for t in parsed.get("created_tasks") or []:
                            created_tasks.append(t)
                    except (json.JSONDecodeError, AttributeError):
                        pass
        else:
            logging.warning(f"[Chat] function calling 超过 {MAX_TOOL_ROUNDS} 轮未收敛")

        logging.warning(f"[Chat raw] {raw_final[:300]}")
        reply, confirmed = _parse_chat_reply(raw_final, mode=mode)
        if not reply:
            reply = FRESH_FALLBACK

        return {
            "reply": reply,
            "confirmed": confirmed,
            "created_tasks": created_tasks,
        }

    except Exception as e:
        logging.error(f"[Chat] API 调用失败: {type(e).__name__}: {e}")
        fallback = MID_CHAT_FALLBACK if has_history else FRESH_FALLBACK
        return {
            "reply": fallback,
            "confirmed": False,
            "created_tasks": [],
        }
