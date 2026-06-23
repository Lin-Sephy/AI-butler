"""手动测试计划模式端到端：function calling + confirmed 信号 + 结构化提取。

流程：
  1. 匿名登录
  2. 新建 session
  3. 建一个"考研"项目（让 DS 有东西可查）
  4. 设置 daily_routine（让 DS 可查作息）
  5. 计划模式聊几轮（多轮打磨）
  6. 用户"就这样" → DS 应输出 confirmed: true
  7. /api/plan/extract 应返回结构化 tasks

用法：
  SMOKE_API_BASE_URL=http://127.0.0.1:8000 python scripts/test_plan_mode.py
"""
import io
import json
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import httpx

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
API_BASE = os.getenv("SMOKE_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def step(msg):
    print(f"\n━━━ {msg} ━━━")


def ok(msg):
    print(f"✅ {msg}")


def fail(msg, resp=None):
    print(f"❌ {msg}")
    if resp is not None:
        print(f"   status={resp.status_code}")
        print(f"   body={resp.text[:500]}")
    sys.exit(1)


def main():
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        fail("需要设置 SUPABASE_URL 和 SUPABASE_ANON_KEY")

    print(f"API: {API_BASE}")
    client = httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0))

    # ─── 1. 匿名登录 ───
    step("Step 1: 匿名登录")
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
    if not token:
        fail(f"没拿到 token：{data}")

    # clock skew 兜底：JWT iat 可能比后端时钟晚一点，等 3 秒再用
    import time
    time.sleep(3)
    ok(f"user_id={user_id[:8]}…")

    auth_headers = {"Authorization": f"Bearer {token}"}
    json_headers = {**auth_headers, "Content-Type": "application/json"}

    # ─── 2. 新 session ───
    step("Step 2: 新 session")
    r = client.post(f"{API_BASE}/api/session/new", headers=auth_headers)
    if r.status_code != 200:
        fail("session/new 失败", r)
    session_id = r.json()["session_id"]
    ok(f"session_id={session_id[:8]}…")

    # ─── 3. 建"考研"项目 ───
    step("Step 3: 建考研项目")
    r = client.post(
        f"{API_BASE}/api/projects",
        headers=json_headers,
        json={
            "name": "考研",
            "keywords": ["考研", "概率论", "数学", "英语阅读"],
            "summary": "数学二轮复习到概率论，英语阅读还没开始，政治暂缓",
        },
    )
    if r.status_code != 200:
        fail("建项目失败", r)
    ok(f"项目 id={r.json().get('id')}")

    # ─── 4. 设日常作息 ───
    step("Step 4: 设日常作息")
    r = client.put(
        f"{API_BASE}/api/profile/daily_routine",
        headers=json_headers,
        json={"routine": "9:00 开始学习；12:00-15:00 休息；18:00-19:00 吃饭；22:00 休息"},
    )
    if r.status_code != 200:
        fail("设作息失败", r)
    ok("作息已设")

    # ─── 5. 计划模式：多轮打磨 ───
    step("Step 5: 计划模式对话（每轮观察 confirmed 字段）")

    def send(msg):
        r = client.post(
            f"{API_BASE}/api/chat",
            headers=json_headers,
            json={"message": msg, "session_id": session_id, "mode": "plan"},
        )
        if r.status_code != 200:
            fail("chat 失败", r)
        data = r.json()
        print(f"\n用户 > {msg}")
        print(f"小白 > {data['reply'][:200]}")
        print(f"[confirmed={data.get('confirmed', False)}]")
        return data

    send("小白，帮我排明天的考研计划")
    send("高数我坐不住，一小时最多了，中间要换换脑子")
    final = send("行，就这样，记下来")

    if not final.get("confirmed"):
        fail(f"用户明确说'记下来'但 confirmed 还是 False！最终回复: {final['reply']}")
    ok("DS 正确识别用户确认，confirmed=True")

    # ─── 6. 结构化提取 ───
    step("Step 6: /api/plan/extract 提取结构化 tasks")
    r = client.post(
        f"{API_BASE}/api/plan/extract",
        headers=json_headers,
        json={"session_id": session_id},
    )
    if r.status_code != 200:
        fail("plan/extract 失败", r)
    extracted = r.json().get("tasks") or []
    if not extracted:
        fail(f"提取到 0 个 task：{r.json()}")

    ok(f"提取到 {len(extracted)} 个 task：")
    for t in extracted:
        print(f"  - {t}")

    # ─── 7. 清理测试项目 ───
    step("Step 7: 清理测试项目")
    projects_resp = client.get(f"{API_BASE}/api/projects", headers=auth_headers)
    for p in projects_resp.json().get("projects", []):
        if p.get("name") == "考研":
            client.delete(f"{API_BASE}/api/projects/{p['id']}", headers=auth_headers)
            ok(f"已删除项目 id={p['id']}")
            break

    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("✅ 计划模式端到端通过")
    print(f"测试用户 {user_id}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


if __name__ == "__main__":
    main()
