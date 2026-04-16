"""Supabase (PostgREST) 数据库操作。

通过 httpx 直接调用 Supabase REST API，无需官方 SDK。
v2 多用户改造（2026-04-15）：所有公开函数第一个参数都是 user_id (UUID 字符串)，
对应 Supabase auth.users.id。后端用 SERVICE_KEY 跑（bypass RLS），所以查询里
**必须手动**带 user_id 过滤——RLS 是 defense-in-depth，不是过滤靠山。
"""

import httpx
import json
from datetime import datetime, timedelta, timezone
import config

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
    resp = httpx.get(f"{_BASE_URL}/{table}", headers=_HEADERS, params=params or {}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _post(table: str, data: dict, return_row: bool = True) -> dict | None:
    """POST 请求（INSERT），可选返回插入的行。"""
    headers = dict(_HEADERS)
    if return_row:
        headers["Prefer"] = "return=representation"
    resp = httpx.post(f"{_BASE_URL}/{table}", headers=headers, json=data, timeout=10)
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
    resp = httpx.patch(f"{_BASE_URL}/{table}", headers=headers, params=params, json=data, timeout=10)
    resp.raise_for_status()
    if return_row:
        rows = resp.json()
        return rows[0] if rows else None
    return None


def _delete(table: str, params: dict) -> None:
    """DELETE 请求。"""
    resp = httpx.delete(f"{_BASE_URL}/{table}", headers=_HEADERS, params=params, timeout=10)
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

def save_chat_message(user_id: str, session_id: str, role: str, content: str) -> None:
    """保存一条聊天消息。"""
    today = now_cn().strftime("%Y-%m-%d")
    _post("chat_session", {
        "user_id": user_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "session_date": today,
        "created_at": now_cn().isoformat(),
    }, return_row=False)


def load_session_messages(user_id: str, session_id: str) -> list[dict]:
    """加载指定 session 的所有聊天消息。"""
    rows = _get("chat_session", {
        "user_id": f"eq.{user_id}",
        "session_id": f"eq.{session_id}",
        "select": "role,content",
        "order": "created_at.asc",
    })
    return [{"role": r["role"], "content": r["content"]} for r in rows]


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
                    energy: int | None = None,
                    intent: str = "", strategy: str = "") -> None:
    """记录用户对推荐的反馈。

    energy 为 None 表示"此刻精力未知"（写 NULL 到 DB），
    intent / strategy 是 MVP 遗产字段，默认空串。
    """
    _post("action_log", {
        "user_id": user_id,
        "energy_at_action": energy,
        "intent": intent,
        "strategy": strategy,
        "recommendation": recommendation,
        "user_action": user_action,
        "timestamp": now_cn().isoformat(),
    }, return_row=False)
