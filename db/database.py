"""Supabase (PostgREST) 数据库操作。

通过 httpx 直接调用 Supabase REST API，无需官方 SDK。
v2 多用户改造（2026-04-15）：所有公开函数第一个参数都是 user_id (UUID 字符串)，
对应 Supabase auth.users.id。后端用 SERVICE_KEY 跑（bypass RLS），所以查询里
**必须手动**带 user_id 过滤——RLS 是 defense-in-depth，不是过滤靠山。
"""

import httpx
import json
import logging
import time
from datetime import datetime, timedelta, timezone
import config
from core.crypto import encrypt_api_key, decrypt_api_key

# Supabase 请求超时和重试配置
# 本地网络到 Singapore 区偶发 SSL handshake 超时（_ssl.c:1063），
# 用 httpx.Client 持久连接复用 TLS session，大幅减少每次握手开销
_TIMEOUT = 15
_MAX_RETRIES = 3      # 含首次，即首次 + 2 次重试
_RETRY_DELAY = 0.4    # 重试前短暂等待，避开 burst 失败

# 触发重试的网络层异常（超时 / 连接错误 / TLS 握手失败）
_RETRYABLE = (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError)

# 全局持久化 Client，复用连接池和 TLS session——
# 第一次建立 TLS 握手后，后续请求走 keep-alive，延迟从 ~500ms 降到 ~20ms
_CLIENT = httpx.Client(
    timeout=_TIMEOUT,
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=60),
)


def _with_retry(method: str, url: str, **kwargs) -> httpx.Response:
    """带重试的 httpx 调用。只重试网络层短暂异常，不重试 4xx/5xx 响应。"""
    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            return _CLIENT.request(method, url, **kwargs)
        except _RETRYABLE as e:
            last_exc = e
            if attempt < _MAX_RETRIES - 1:
                logging.warning(
                    f"[DB] {method} {url.rsplit('/', 1)[-1]} 失败 {type(e).__name__}，"
                    f"{_RETRY_DELAY}s 后重试（剩 {_MAX_RETRIES - attempt - 1} 次）"
                )
                time.sleep(_RETRY_DELAY)
    assert last_exc is not None
    raise last_exc

# 北京时间 UTC+8
_CN_TZ = timezone(timedelta(hours=8))


def now_cn() -> datetime:
    """返回当前北京时间。"""
    return datetime.now(_CN_TZ)


# ---- Supabase REST 客户端 ----

_BASE_URL = config.SUPABASE_URL + "/rest/v1"
_HEADERS = {
    "apikey": config.SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
}


def _get(table: str, params: dict | None = None) -> list[dict]:
    """GET 请求，返回行列表。"""
    resp = _with_retry("GET", f"{_BASE_URL}/{table}", headers=_HEADERS, params=params or {})
    resp.raise_for_status()
    return resp.json()


def _post(table: str, data: dict, return_row: bool = True) -> dict | None:
    """POST 请求（INSERT），可选返回插入的行。"""
    headers = dict(_HEADERS)
    if return_row:
        headers["Prefer"] = "return=representation"
    resp = _with_retry("POST", f"{_BASE_URL}/{table}", headers=headers, json=data)
    resp.raise_for_status()
    if return_row:
        rows = resp.json()
        return rows[0] if rows else None
    return None


def _patch(table: str, params: dict, data: dict, return_row: bool = True) -> dict | None:
    """PATCH 请求（UPDATE），params 用于过滤行。"""
    headers = dict(_HEADERS)
    if return_row:
        headers["Prefer"] = "return=representation"
    resp = _with_retry("PATCH", f"{_BASE_URL}/{table}", headers=headers, params=params, json=data)
    resp.raise_for_status()
    if return_row:
        rows = resp.json()
        return rows[0] if rows else None
    return None


def _delete(table: str, params: dict) -> None:
    """DELETE 请求。"""
    resp = _with_retry("DELETE", f"{_BASE_URL}/{table}", headers=_HEADERS, params=params)
    resp.raise_for_status()


def init_db():
    """Supabase 表已通过 SQL Editor 创建，此函数仅做兼容保留。"""
    pass


# ════════════════════════════════════════════════════════════
# 以下所有公开函数：第一个参数 user_id = Supabase auth.users.id
# user_profile 表的 PK 是 user_id；其他表用 user_id 列过滤
# ════════════════════════════════════════════════════════════


def _get_profile_field(user_id: str, field: str, default: str = "") -> str:
    """读 user_profile 表的单个字段，无行或空值返回 default。"""
    rows = _get("user_profile", {"user_id": f"eq.{user_id}", "select": field})
    if rows and rows[0].get(field):
        return rows[0][field]
    return default


def _set_profile_field(user_id: str, field: str, value: str) -> None:
    """写 user_profile 表的单个字段。"""
    _patch("user_profile", {"user_id": f"eq.{user_id}"}, {field: value}, return_row=False)


# ---- user_memo / ai_memo / daily_memo CRUD ----

def get_user_memo(user_id: str) -> str:
    return _get_profile_field(user_id, "user_memo")


def save_user_memo(user_id: str, memo: str) -> None:
    _set_profile_field(user_id, "user_memo", memo)


def get_ai_memo(user_id: str) -> str:
    return _get_profile_field(user_id, "ai_memo")


def save_ai_memo(user_id: str, memo: str) -> None:
    _set_profile_field(user_id, "ai_memo", memo)


def clear_ai_memo(user_id: str) -> None:
    _set_profile_field(user_id, "ai_memo", "")


def get_daily_memo(user_id: str) -> str:
    """每日记忆 JSON 字符串，默认 '{}'。"""
    return _get_profile_field(user_id, "daily_memo", "{}")


def save_daily_memo(user_id: str, memo: str) -> None:
    _set_profile_field(user_id, "daily_memo", memo)


# ---- 跟宠名字 + 自定义人格 CRUD ----

def get_companion_name(user_id: str) -> str:
    return _get_profile_field(user_id, "companion_name", "小白")


def save_companion_name(user_id: str, name: str) -> None:
    _set_profile_field(user_id, "companion_name", name)


def get_custom_persona(user_id: str) -> str:
    """自定义人格描述，空字符串表示用 MBTI 预设。"""
    return _get_profile_field(user_id, "custom_persona")


def save_custom_persona(user_id: str, persona: str) -> None:
    _set_profile_field(user_id, "custom_persona", persona)


def get_full_profile(user_id: str) -> dict:
    """一次 SELECT * 拿 user_profile 所有字段，避免 /api/chat 里多次重复读。

    返回字段：companion_name, custom_persona, user_memo, ai_memo, daily_memo,
              daily_routine, llm_provider, llm_base_url, llm_model, llm_api_key 等。
              没填写的返回空字符串（非 None）。
    """
    rows = _get("user_profile", {
        "user_id": f"eq.{user_id}",
        "select": "*",
    })
    if not rows:
        return {}
    row = rows[0]
    # 统一把 None 归一成空串 / 空 json，调用方少判空
    return {
        "companion_name": row.get("companion_name") or "小白",
        "custom_persona": row.get("custom_persona") or "",
        "user_memo": row.get("user_memo") or "",
        "ai_memo": row.get("ai_memo") or "",
        "daily_memo": row.get("daily_memo") or "{}",
        "daily_routine": row.get("daily_routine") or "",
        "llm_provider": row.get("llm_provider") or "",
        "llm_base_url": row.get("llm_base_url") or "",
        "llm_model": row.get("llm_model") or "",
        "llm_api_key": decrypt_api_key(row.get("llm_api_key") or ""),
    }


def get_llm_config(user_id: str) -> dict:
    """读用户自带 LLM 配置（BYOK）。返回 dict，字段为空表示用户没设。

    调用方判断：如果 api_key/base_url/model 都有值 → 用用户配置；否则回退默认 DeepSeek。
    """
    rows = _get("user_profile", {
        "user_id": f"eq.{user_id}",
        "select": "llm_provider,llm_base_url,llm_model,llm_api_key",
    })
    if not rows:
        return {"provider": "", "base_url": "", "model": "", "api_key": ""}
    row = rows[0]
    return {
        "provider": row.get("llm_provider") or "",
        "base_url": row.get("llm_base_url") or "",
        "model": row.get("llm_model") or "",
        "api_key": decrypt_api_key(row.get("llm_api_key") or ""),
    }


def save_llm_config(user_id: str, provider: str, base_url: str, model: str,
                    api_key: str | None = None) -> None:
    """保存用户 LLM 配置。api_key=None 表示不更新（保留原值）；""（空串）表示清空。"""
    data = {
        "llm_provider": provider,
        "llm_base_url": base_url,
        "llm_model": model,
    }
    if api_key is not None:
        # 空串照样存空串（清空操作），非空才走加密
        data["llm_api_key"] = encrypt_api_key(api_key) if api_key else ""

    # upsert：没 row 就插，有就 patch
    existing = _get("user_profile", {"user_id": f"eq.{user_id}", "select": "user_id"})
    if existing:
        _patch("user_profile", {"user_id": f"eq.{user_id}"}, data, return_row=False)
    else:
        data["user_id"] = user_id
        _post("user_profile", data, return_row=False)


def get_companion_profile(user_id: str) -> dict:
    """一次取出跟宠名字 + 自定义人格，省一次数据库请求。

    返回 {"name": str, "custom_persona": str}
    """
    rows = _get("user_profile", {
        "user_id": f"eq.{user_id}",
        "select": "companion_name,custom_persona",
    })
    if not rows:
        return {"name": "小白", "custom_persona": ""}
    row = rows[0]
    return {
        "name": row.get("companion_name") or "小白",
        "custom_persona": row.get("custom_persona") or "",
    }


# ---- chat_session CRUD ----

def save_chat_message(user_id: str, session_id: str, role: str, content: str, mode: str = "chat") -> None:
    """保存一条聊天消息。mode: 'chat' | 'plan'，用于后续分流加载。"""
    today = now_cn().strftime("%Y-%m-%d")
    _post("chat_session", {
        "user_id": user_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "mode": mode,
        "session_date": today,
        "created_at": now_cn().isoformat(),
    }, return_row=False)


def load_session_messages(user_id: str, session_id: str, mode: str | None = None) -> list[dict]:
    """加载指定 session 的聊天消息。

    mode=None: 拉全部（给 UI 展示，每条带 mode 字段）
    mode='chat': 只拉 mode='chat' 或 mode=NULL 的消息（老数据 NULL 视作闲聊）
    mode='plan': 只拉 mode='plan' 的消息（严格；老数据不出现在 plan 历史里）
    """
    params = {
        "user_id": f"eq.{user_id}",
        "session_id": f"eq.{session_id}",
        "select": "role,content,mode",
        "order": "created_at.asc",
    }
    if mode == "chat":
        # PostgREST or 过滤：mode='chat' 或 mode IS NULL
        params["or"] = "(mode.eq.chat,mode.is.null)"
    elif mode == "plan":
        params["mode"] = "eq.plan"
    # mode=None 不加过滤，全量

    rows = _get("chat_session", params)
    return [
        {
            "role": r["role"],
            "content": r["content"],
            "mode": r.get("mode") or "chat",  # NULL 归一成 'chat'
        }
        for r in rows
    ]


# ---- 精力记录 CRUD ----

def save_energy(user_id: str, energy_level: int, source: str) -> dict:
    """写入一条精力记录，返回写入结果。"""
    now = now_cn().isoformat()
    _post("energy_log", {
        "user_id": user_id,
        "energy_level": energy_level,
        "source": source,
        "created_at": now,
    }, return_row=False)
    return {"energy_level": energy_level, "source": source, "updated_at": now}


def get_today_energy(user_id: str) -> dict | None:
    """获取今天最新一条精力记录，没有则返回 None。"""
    today_start = now_cn().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    rows = _get("energy_log", {
        "user_id": f"eq.{user_id}",
        "created_at": f"gte.{today_start}",
        "select": "energy_level,source,created_at",
        "order": "created_at.desc",
        "limit": "1",
    })
    if rows:
        return {
            "energy_level": rows[0]["energy_level"],
            "source": rows[0]["source"],
            "updated_at": rows[0]["created_at"],
        }
    return None


def get_avg_energy_7d(user_id: str) -> float | None:
    """过去 7 天精力均值（每天取最后一条），无数据返回 None。"""
    seven_days_ago = (now_cn() - timedelta(days=7)).isoformat()
    rows = _get("energy_log", {
        "user_id": f"eq.{user_id}",
        "created_at": f"gte.{seven_days_ago}",
        "select": "energy_level,created_at",
        "order": "created_at.desc",
    })
    if not rows:
        return None

    daily = {}
    for r in rows:
        day = r["created_at"][:10]  # YYYY-MM-DD
        if day not in daily:
            daily[day] = r["energy_level"]

    return sum(daily.values()) / len(daily)


# ---- action_log CRUD ----

def save_action_log(user_id: str, recommendation: str, user_action: str,
                    energy: int | None = None) -> None:
    """记录用户对推荐的反馈。

    energy 为 None 表示"此刻精力未知"（写 NULL 到 DB）。
    DB 里还留着 intent / strategy 两个 v4 遗留 nullable 列，等 migrate 统一删（死代码清单 #3）。
    """
    _post("action_log", {
        "user_id": user_id,
        "energy_at_action": energy,
        "recommendation": recommendation,
        "user_action": user_action,
        "timestamp": now_cn().isoformat(),
    }, return_row=False)


# ════════════════════════════════════════════════════════════
# v5.0 新增：daily_routine + project CRUD + 最近 N 天任务查询
# ════════════════════════════════════════════════════════════


# ---- daily_routine（用户日常作息文本） ----

def get_daily_routine(user_id: str) -> str:
    return _get_profile_field(user_id, "daily_routine")


def save_daily_routine(user_id: str, routine: str) -> None:
    _set_profile_field(user_id, "daily_routine", routine)


# ---- project CRUD ----

def create_project(user_id: str, name: str, keywords: list[str],
                   summary: str = "") -> dict:
    """创建项目。keywords 是关键词列表（Postgres TEXT[]）。"""
    return _post("project", {
        "user_id": user_id,
        "name": name,
        "keywords": keywords,
        "summary": summary,
    })


def list_projects(user_id: str) -> list[dict]:
    """返回该用户所有项目，按最近更新排序。"""
    return _get("project", {
        "user_id": f"eq.{user_id}",
        "select": "*",
        "order": "updated_at.desc",
    })


def get_project(user_id: str, project_id: int) -> dict | None:
    rows = _get("project", {
        "user_id": f"eq.{user_id}",
        "id": f"eq.{project_id}",
        "select": "*",
    })
    return rows[0] if rows else None


def get_project_by_name(user_id: str, name: str) -> dict | None:
    """按项目名精确匹配。给 function calling 的 query_project 工具用。"""
    rows = _get("project", {
        "user_id": f"eq.{user_id}",
        "name": f"eq.{name}",
        "select": "*",
    })
    return rows[0] if rows else None


def update_project(user_id: str, project_id: int, **fields) -> dict | None:
    """更新项目字段。只允许改 name / keywords / summary。"""
    allowed = {"name", "keywords", "summary"}
    data = {k: v for k, v in fields.items() if k in allowed}
    if not data:
        return get_project(user_id, project_id)
    return _patch("project", {
        "user_id": f"eq.{user_id}",
        "id": f"eq.{project_id}",
    }, data)


def delete_project(user_id: str, project_id: int) -> None:
    _delete("project", {
        "user_id": f"eq.{user_id}",
        "id": f"eq.{project_id}",
    })


def find_projects_matching_keyword(user_id: str, text: str) -> list[dict]:
    """遍历用户的所有项目，返回 keywords 中任意词在 text 里出现的项目。

    纯 Python 匹配（不走 DB 的 array 查询），因为关键词命中要做子串匹配，
    DB 的 @> 等操作符是完全等值比较，用不上。项目数一般个位数，O(n*m) 可接受。
    """
    projects = list_projects(user_id)
    hits = []
    for p in projects:
        kws = p.get("keywords") or []
        if any(kw and kw in text for kw in kws):
            hits.append(p)
    return hits


# ---- 最近 N 天任务查询（给 function calling 和第 4 页统计共用） ----

# abandoned 任务查询保留天数：超过就不在"最近 N 天"结果里出现，避免陈年旧账污染 DS 视野
ABANDONED_RETENTION_DAYS = 2


def get_tasks_recent(user_id: str, days: int = 7) -> list[dict]:
    """返回最近 N 天内 created_at 的任务。

    abandoned 状态的任务额外受 ABANDONED_RETENTION_DAYS 过滤：
    completed_at 超过 N 天的不返回，让 DS 的 query_tasks / query_schedule 视野只看到近期真实活动。
    """
    now = now_cn()
    since = (now - timedelta(days=days)).isoformat()
    abandoned_cutoff = (now - timedelta(days=ABANDONED_RETENTION_DAYS)).isoformat()
    tasks = _get("task", {
        "user_id": f"eq.{user_id}",
        "created_at": f"gte.{since}",
        "select": "*",
        "order": "created_at.desc",
    })
    return [
        t for t in tasks
        if t.get("status") != "abandoned"
        or (t.get("completed_at") or "") >= abandoned_cutoff
    ]


def get_completed_tasks_all(user_id: str) -> list[dict]:
    """该用户所有 completed task 的 completed_at + default_minutes（供数据页累计统计）。
    只拉必需两列，减少传输量；行数大时不会爆。"""
    return _get("task", {
        "user_id": f"eq.{user_id}",
        "status": "eq.completed",
        "select": "completed_at,default_minutes",
    })


def get_tasks_by_project(user_id: str, project_id: int) -> list[dict]:
    """某项目下的所有任务，按创建时间倒序。"""
    return _get("task", {
        "user_id": f"eq.{user_id}",
        "project_id": f"eq.{project_id}",
        "select": "*",
        "order": "created_at.desc",
    })
