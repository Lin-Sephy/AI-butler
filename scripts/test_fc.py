"""Step 0: DeepSeek Function Calling 质量实测。

验证 DS 在计划模式下能否:
1. 在该调工具时调（召回）
2. 选对工具（精度）
3. 参数格式合法（可解析）
4. 能处理需要多个工具的场景

通过标准：工具选择准确率 ≥ 80%，参数格式 100% 合法。
不通过则退回 Python 预塞数据方案或合并工具。

用法：python scripts/test_fc.py
"""
import json
import sys
import io
from pathlib import Path

# Windows 强制 UTF-8 输出，不然 emoji / 中文崩
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 让脚本能直接跑
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from openai import OpenAI
import config


# ---- Mock 数据（真实项目里会从 DB 查） ----

MOCK_TASKS_7D = [
    {"date": "2026-04-19", "keyword": "写论文第三章", "minutes": 85, "status": "completed"},
    {"date": "2026-04-19", "keyword": "英语阅读", "minutes": 45, "status": "completed"},
    {"date": "2026-04-18", "keyword": "概率论", "minutes": 0, "status": "abandoned"},
    {"date": "2026-04-18", "keyword": "写论文第三章", "minutes": 60, "status": "completed"},
    {"date": "2026-04-17", "keyword": "改导师批注", "minutes": 30, "status": "paused"},
    {"date": "2026-04-16", "keyword": "写论文第三章", "minutes": 90, "status": "completed"},
]

MOCK_STATS = {
    "最常专注时段": "上午 10-12 点",
    "平均专注时长": "52 分钟",
    "完成率": "78%",
    "最近一周总时长": "6.5 小时",
    "最常做的事": ["写论文第三章 (3次)", "英语阅读 (2次)", "改导师批注 (1次)"],
}

MOCK_PROJECTS = {
    "毕业论文": {
        "summary": "第三章初稿已写完，导师要求重写分析部分，deadline 下周五",
        "关联任务": [
            {"keyword": "写论文第三章", "最后一次": "2026-04-19"},
            {"keyword": "改导师批注", "最后一次": "2026-04-17"},
        ],
    },
    "考研": {
        "summary": "数学二轮复习到概率论，英语阅读还没开始，政治暂缓",
        "关联任务": [
            {"keyword": "概率论", "最后一次": "2026-04-18"},
            {"keyword": "英语阅读", "最后一次": "2026-04-19"},
        ],
    },
}

MOCK_SCHEDULE = {
    "今日事件": [
        {"time": "14:00", "event": "导师 meeting"},
    ],
    "日常作息": "8:30 开始学习；12:00-15:00 休息；18:00-19:00 吃饭；22:00 休息",
}


# ---- 工具定义（开工文档里给的版本） ----

PLAN_MODE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_tasks",
            "description": "查最近几天的任务记录明细（哪天做了什么、做了多久、完成没有）",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "查询最近多少天，默认 7"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_stats",
            "description": "查用户的专注统计（最常专注的时段、平均时长、完成率）",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_project",
            "description": "查某个项目的摘要和关联任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "项目名称，如'毕业论文'、'考研'"}
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_schedule",
            "description": "查今天的日程（具体事件和日常作息）",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# ---- Mock 工具执行 ----

def execute_tool(name: str, args: dict) -> str:
    """模拟工具执行，返回 JSON 字符串给 DS。"""
    if name == "query_tasks":
        days = args.get("days", 7)
        return json.dumps({"days": days, "records": MOCK_TASKS_7D}, ensure_ascii=False)
    if name == "query_stats":
        return json.dumps(MOCK_STATS, ensure_ascii=False)
    if name == "query_project":
        project_name = args.get("name", "")
        matched = {k: v for k, v in MOCK_PROJECTS.items() if project_name in k or k in project_name}
        if not matched:
            return json.dumps({"error": f"没找到项目 '{project_name}'", "可选": list(MOCK_PROJECTS.keys())}, ensure_ascii=False)
        return json.dumps(matched, ensure_ascii=False)
    if name == "query_schedule":
        return json.dumps(MOCK_SCHEDULE, ensure_ascii=False)
    return json.dumps({"error": f"未知工具 {name}"}, ensure_ascii=False)


# ---- 测试场景 ----

SYSTEM_PROMPT = """你叫"小白"，一只成了精的白鼬，铲屎官是你的朋友。

你的铲屎官现在需要你帮忙梳理计划。"""

TEST_CASES = [
    {
        "user": "帮我排明天的考研计划",
        "expected_tools": ["query_schedule", "query_project"],  # 可能也会调 stats/tasks
        "desc": "日计划场景——应该查日程 + 考研项目",
    },
    {
        "user": "我论文做到哪了？",
        "expected_tools": ["query_project"],
        "desc": "项目进度查询——应该查毕业论文项目",
    },
    {
        "user": "我最近效率咋样",
        "expected_tools": ["query_stats"],
        "desc": "统计查询——应该调 stats",
    },
    {
        "user": "我这周都做了什么",
        "expected_tools": ["query_tasks"],
        "desc": "任务历史——应该查 tasks",
    },
    {
        "user": "今天下午有啥安排",
        "expected_tools": ["query_schedule"],
        "desc": "日程查询——应该调 schedule",
    },
]


# ---- 跑一轮 ----

def run_case(client: OpenAI, case: dict, trial: int) -> dict:
    """跑一个测试 case，返回结果 dict。"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": case["user"]},
    ]

    tools_called = []
    param_errors = []
    max_rounds = 4
    final_reply = ""

    for round_idx in range(max_rounds):
        try:
            resp = client.chat.completions.create(
                model=config.DEEPSEEK_MODEL,
                messages=messages,
                tools=PLAN_MODE_TOOLS,
                temperature=0.7,
                max_tokens=600,
            )
        except Exception as e:
            return {"error": f"API 调用失败: {type(e).__name__}: {e}"}

        msg = resp.choices[0].message

        # 把 assistant 消息加回上下文
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            final_reply = msg.content or ""
            break

        # 执行每个工具调用
        for tc in msg.tool_calls:
            name = tc.function.name
            raw_args = tc.function.arguments
            try:
                args = json.loads(raw_args) if raw_args else {}
                tools_called.append({"name": name, "args": args})
                result = execute_tool(name, args)
            except json.JSONDecodeError as e:
                param_errors.append({"tool": name, "raw_args": raw_args, "error": str(e)})
                result = json.dumps({"error": "参数格式错误"}, ensure_ascii=False)
                tools_called.append({"name": name, "args": None, "parse_error": str(e)})

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    return {
        "tools_called": tools_called,
        "param_errors": param_errors,
        "final_reply": final_reply,
        "rounds": round_idx + 1,
    }


# ---- 主流程 ----

def main():
    if not config.DEEPSEEK_API_KEY:
        print("ERROR: DEEPSEEK_API_KEY 未设置")
        sys.exit(1)

    client = OpenAI(
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL,
        timeout=httpx.Timeout(60.0, connect=10.0),
        max_retries=1,
    )

    TRIALS_PER_CASE = 2
    all_results = []
    total_called_correct = 0
    total_expected = 0
    total_param_errors = 0
    total_api_errors = 0

    for case in TEST_CASES:
        print(f"\n{'='*60}")
        print(f"场景：{case['desc']}")
        print(f"用户：{case['user']}")
        print(f"期望工具：{case['expected_tools']}")
        print(f"{'='*60}")

        for trial in range(TRIALS_PER_CASE):
            result = run_case(client, case, trial)

            if "error" in result:
                print(f"  [trial {trial+1}] API ERROR: {result['error']}")
                total_api_errors += 1
                continue

            tools_called_names = [t["name"] for t in result["tools_called"]]
            hit = set(case["expected_tools"]) & set(tools_called_names)

            print(f"\n  [trial {trial+1}] 调了 {len(tools_called_names)} 次工具：{tools_called_names}")
            for t in result["tools_called"]:
                print(f"    - {t['name']}({t.get('args', t)})")
            if result["param_errors"]:
                print(f"    !! 参数错误：{result['param_errors']}")
                total_param_errors += len(result["param_errors"])
            print(f"    DS 最终回复：{result['final_reply'][:120]}")
            print(f"    命中期望：{list(hit)} / 期望 {case['expected_tools']}")

            total_expected += len(case["expected_tools"])
            total_called_correct += len(hit)

            all_results.append({
                "case": case["desc"],
                "trial": trial + 1,
                "tools_called": tools_called_names,
                "expected": case["expected_tools"],
                "hit": list(hit),
                "param_errors": result["param_errors"],
            })

    # 汇总
    print(f"\n\n{'#'*60}")
    print("总结")
    print(f"{'#'*60}")
    total_runs = len(TEST_CASES) * TRIALS_PER_CASE
    effective_runs = total_runs - total_api_errors

    print(f"总场景数：{len(TEST_CASES)}，每场景 {TRIALS_PER_CASE} 次，合计 {total_runs} 次")
    print(f"API 失败：{total_api_errors}")
    if effective_runs > 0:
        # 召回率：期望工具被调的比例
        recall = total_called_correct / total_expected * 100 if total_expected else 0
        param_ok_rate = (1 - total_param_errors / max(1, sum(len(r['tools_called']) for r in all_results))) * 100
        print(f"工具召回率：{recall:.1f}%（期望调用数 {total_expected}，实际命中 {total_called_correct}）")
        print(f"参数格式合法率：{param_ok_rate:.1f}%")
        print()
        print(f"通过标准：召回率 ≥ 80%，参数合法率 = 100%")
        if recall >= 80 and total_param_errors == 0:
            print("✅ 通过")
        else:
            print("❌ 不通过，需要讨论应对方案")


if __name__ == "__main__":
    main()
