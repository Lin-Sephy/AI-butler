"""计划结构化提取：用户确认计划后，从对话里抽出可写入 task 表的结构化 tasks。

v5.0 架构：
- 计划模式下 DS 输出 ---judgment---{"confirmed": true} 时，前端请求这个提取
- 单独一次 LLM 调用，prompt 只做"从对话里提取 tasks"这一件事（LLM 做判断，Python 做执行）
- 返回的是候选列表，前端让用户确认/修改后批量写入 task 表

与 call_task 的区别：
- call_task 是 v4 单任务推荐，带精力校验、守门规则等
- plan_extract 可能返回多个 task，不做推荐只做提取，纯结构化抽取
"""

import json
import logging
import httpx
from openai import OpenAI
import config

from db.database import list_projects


EXTRACT_TASKS_PROMPT = """你是一个任务结构化助手。下面是"铲屎官"（用户）和 AI 助手关于安排计划的对话。

用户刚才表示"定稿"了这份计划。你的任务是从对话里提取这份最终版计划，把它拆成一条条具体的 task，返回结构化 JSON。

用户的项目清单（用于关联）：
{projects_context}

当前日期：{today}

返回 JSON，不要包含其他内容：
{{
  "tasks": [
    {{
      "keyword": "任务的简短描述（铲屎官原话优先，必填）",
      "minutes": 25 或 null,
      "task_type": "work 或 rest",
      "scheduled_at": "YYYY-MM-DD HH:MM 或 null",
      "project_name": "匹配的项目名 或 null"
    }}
  ]
}}

规则：
- 只提取对话里"定稿"了的 task，不包括聊过但被改掉或推翻的
- keyword 用铲屎官的原话（"写论文第三章"），不要 AI 加的修饰
- minutes：铲屎官明确说了时长就用；没说、但是典型工作学习任务填 25-90 的合理值；休息类、无法估的填 null
- task_type：工作学习类填 "work"，休息放松类填 "rest"
- scheduled_at：仅当对话明确说了开始时间才填；只说"上午/下午"这种模糊时间填 null
- project_name：如果 task 的 keyword 跟项目清单里某个项目相关，填那个项目的名字；否则 null
- 如果对话里没有任何明确定稿的 task，返回 {{"tasks": []}}"""


def extract_tasks_from_conversation(user_id: str, chat_history: list,
                                    max_messages: int = 30) -> list[dict]:
    """从对话中提取结构化的 tasks 列表。

    调用方通常是 /api/plan/extract 端点，在 DS 输出 confirmed=true 后触发。
    """
    if not config.DEEPSEEK_API_KEY or not chat_history:
        return []

    try:
        projects = list_projects(user_id)
    except Exception as e:
        logging.warning(f"[PlanExtract] 读取项目失败: {type(e).__name__}: {e}")
        projects = []
    project_names = [p["name"] for p in projects]
    projects_context = "、".join(project_names) if project_names else "（还没建项目）"

    from db.database import now_cn
    today = now_cn().strftime("%Y-%m-%d")

    recent = chat_history[-max_messages:]
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
        prompt = EXTRACT_TASKS_PROMPT.format(
            projects_context=projects_context,
            today=today,
        )
        resp = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            temperature=0.2,
            max_tokens=1500,
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
        logging.error(f"[PlanExtract] 提取失败: {type(e).__name__}: {e}")
        return []

    tasks_raw = result.get("tasks") or []
    if not isinstance(tasks_raw, list):
        return []

    # 项目名 → id 映射
    project_id_by_name = {p["name"]: p["id"] for p in projects}

    tasks = []
    for t in tasks_raw:
        if not isinstance(t, dict):
            continue
        keyword = (t.get("keyword") or "").strip()
        if not keyword:
            continue

        task_type = t.get("task_type")
        if task_type not in ("work", "rest"):
            task_type = "work"

        minutes = t.get("minutes")
        if minutes is not None:
            try:
                minutes = max(5, min(180, int(minutes)))
            except (TypeError, ValueError):
                minutes = None

        scheduled_at = t.get("scheduled_at")
        if scheduled_at:
            from datetime import datetime
            try:
                datetime.strptime(scheduled_at, "%Y-%m-%d %H:%M")
            except (TypeError, ValueError):
                scheduled_at = None
        else:
            scheduled_at = None

        project_name = t.get("project_name")
        project_id = project_id_by_name.get(project_name) if project_name else None

        tasks.append({
            "keyword": keyword,
            "minutes": minutes,
            "task_type": task_type,
            "scheduled_at": scheduled_at,
            "project_name": project_name if project_id else None,
            "project_id": project_id,
        })

    return tasks
