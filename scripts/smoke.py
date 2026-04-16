"""L2 集成 smoke：端到端验证后端核心链路。

流程：
  1. 匿名登录拿 JWT（Supabase /auth/v1/signup）
  2. GET /api/tasks/today → 新用户应为空
  3. POST /api/session/new → 拿 session_id
  4. POST /api/chat → AI 回复 + 信号（耗一次 DeepSeek 调用）
  5. POST /api/task/record → 建任务
  6. GET /api/tasks/today → 验证任务出现
  7. POST /api/task/{id}/complete → 标记完成

用法：
  python scripts/smoke.py

环境变量：
  SUPABASE_URL, SUPABASE_ANON_KEY（从项目 .env 读）
  SMOKE_API_BASE_URL（可选，默认 Render 部署地址）

副作用：
  每次运行在 Supabase auth.users 里建一个匿名用户（加上 user_profile / task 等数据）。
  免费套餐下累积也还好，量大了再考虑加清理脚本。
"""

import os
import sys
import httpx

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
API_BASE = os.getenv("SMOKE_API_BASE_URL", "https://ai-butler-1sp8.onrender.com").rstrip("/")


def step(n: int, desc: str) -> None:
    print(f"\n━━━ Step {n}: {desc} ━━━")


def ok(msg: str) -> None:
    print(f"✅ {msg}")


def fail(msg: str, resp: httpx.Response | None = None) -> None:
    print(f"❌ {msg}")
    if resp is not None:
        print(f"   status: {resp.status_code}")
        print(f"   body:   {resp.text[:500]}")
    sys.exit(1)


def main() -> None:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        fail("缺 SUPABASE_URL / SUPABASE_ANON_KEY，在项目根 .env 里配好再跑")

    print(f"Supabase: {SUPABASE_URL}")
    print(f"API:      {API_BASE}")
    print("(Render free 冷启动 30-50s，本机 VPN 在路径上会更慢；read 超时 120s)")

    # connect 快速失败，read 给冷启动和 DeepSeek 调用留足时间
    client = httpx.Client(timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0))

    # ─── Step 1: 匿名登录 ───
    step(1, "匿名登录拿 JWT")
    r = client.post(
        f"{SUPABASE_URL}/auth/v1/signup",
        headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
        json={},
    )
    if r.status_code not in (200, 201):
        fail("signup 失败", r)
    data = r.json()
    token = data.get("access_token") or data.get("session", {}).get("access_token")
    user_id = data.get("user", {}).get("id")
    if not token or not user_id:
        fail(f"signup 返回缺字段：{data}")
    ok(f"user_id={user_id[:8]}…")

    auth_headers = {"Authorization": f"Bearer {token}"}
    json_headers = {**auth_headers, "Content-Type": "application/json"}

    # ─── Step 2: 空列表 ───
    step(2, "GET /api/tasks/today（新用户应为空，首次调用可能冷启动 30-120s）")
    r = client.get(f"{API_BASE}/api/tasks/today", headers=auth_headers)
    if r.status_code != 200:
        fail("tasks/today 失败", r)
    tasks = r.json().get("tasks", [])
    if tasks:
        fail(f"新用户不该有任务：{tasks}")
    ok('返回 {"tasks": []}')

    # ─── Step 3: 新会话 ───
    step(3, "POST /api/session/new")
    r = client.post(f"{API_BASE}/api/session/new", headers=auth_headers)
    if r.status_code != 200:
        fail("session/new 失败", r)
    session_data = r.json()
    session_id = session_data.get("session_id")
    if not session_id:
        fail(f"session/new 返回缺 session_id：{session_data}")
    ok(f"session_id={session_id[:8]}…")

    # ─── Step 4: 聊天 ───
    step(4, "POST /api/chat（耗一次 DeepSeek 调用）")
    r = client.post(
        f"{API_BASE}/api/chat",
        headers=json_headers,
        json={
            "message": "你好，今天想写一会儿论文",
            "session_id": session_id,
            "persona": "infp",
        },
    )
    if r.status_code != 200:
        fail("chat 失败", r)
    chat = r.json()
    reply = chat.get("reply", "")
    if not reply:
        fail(f"chat 返回没有 reply：{chat}")
    sig = chat.get("signal", {})
    ok(f"AI 回复 {len(reply)} 字（signal.activity_category={sig.get('activity_category')}, user_attitude={sig.get('user_attitude')}）")

    # ─── Step 5: 记录任务 ───
    step(5, "POST /api/task/record")
    r = client.post(
        f"{API_BASE}/api/task/record",
        headers=json_headers,
        json={
            "task_keyword": "smoke 测试任务",
            "suggested_minutes": 25,
            "task_type": "work",
        },
    )
    if r.status_code != 200:
        fail("task/record 失败", r)
    task_data = r.json()
    task_id = task_data.get("task", {}).get("id")
    if not task_id:
        fail(f"task/record 返回缺 task.id：{task_data}")
    ok(f"task_id={task_id}")

    # ─── Step 6: 验证出现 ───
    step(6, "GET /api/tasks/today（应含刚记录的）")
    r = client.get(f"{API_BASE}/api/tasks/today", headers=auth_headers)
    tasks = r.json().get("tasks", [])
    if not any(t.get("id") == task_id for t in tasks):
        fail(f"刚记录的任务 {task_id} 没出现：{tasks}")
    ok(f"任务在列表中（共 {len(tasks)} 条）")

    # ─── Step 7: 完成 ───
    step(7, f"POST /api/task/{task_id}/complete")
    r = client.post(f"{API_BASE}/api/task/{task_id}/complete", headers=auth_headers)
    if r.status_code != 200:
        fail("complete 失败", r)
    ok("任务标记完成")

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("✅ 全部 7 步通过")
    print(f"测试用户 {user_id} 留在 Supabase auth.users，累计多了手动清")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


if __name__ == "__main__":
    main()
