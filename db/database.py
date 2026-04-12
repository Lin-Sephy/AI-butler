"""Supabase (PostgREST) 数据库操作，替代原 SQLite 版本。

通过 httpx 直接调用 Supabase REST API，无需官方 SDK。
所有函数签名与原版保持一致，core/ 层不需要改动。
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


# ---- user_memo CRUD ----

def get_user_memo() -> str:
    """获取用户手记内容。"""
    rows = _get("user_profile", {"id": "eq.default_user", "select": "user_memo"})
    if rows and rows[0].get("user_memo"):
        return rows[0]["user_memo"]
    return ""


def save_user_memo(memo: str) -> None:
    """保存用户手记内容。"""
    _patch("user_profile", {"id": "eq.default_user"}, {"user_memo": memo}, return_row=False)


def get_ai_memo() -> str:
    """获取 AI 自动记忆内容。"""
    rows = _get("user_profile", {"id": "eq.default_user", "select": "ai_memo"})
    if rows and rows[0].get("ai_memo"):
        return rows[0]["ai_memo"]
    return ""


def save_ai_memo(memo: str) -> None:
    """保存 AI 自动记忆内容。"""
    _patch("user_profile", {"id": "eq.default_user"}, {"ai_memo": memo}, return_row=False)


def clear_ai_memo() -> None:
    """清空 AI 自动记忆。"""
    _patch("user_profile", {"id": "eq.default_user"}, {"ai_memo": ""}, return_row=False)


def get_daily_memo() -> str:
    """获取每日记忆 JSON 字符串。"""
    rows = _get("user_profile", {"id": "eq.default_user", "select": "daily_memo"})
    if rows and rows[0].get("daily_memo"):
        return rows[0]["daily_memo"]
    return "{}"


def save_daily_memo(memo: str) -> None:
    """保存每日记忆 JSON 字符串。"""
    _patch("user_profile", {"id": "eq.default_user"}, {"daily_memo": memo}, return_row=False)


# ---- 跟宠名字 + 自定义人格 CRUD ----

def get_companion_name() -> str:
    """获取跟宠名字，默认 '小白'。"""
    rows = _get("user_profile", {"id": "eq.default_user", "select": "companion_name"})
    if rows and rows[0].get("companion_name"):
        return rows[0]["companion_name"]
    return "小白"


def save_companion_name(name: str) -> None:
    """保存跟宠名字。"""
    _patch("user_profile", {"id": "eq.default_user"}, {"companion_name": name}, return_row=False)


def get_custom_persona() -> str:
    """获取自定义人格描述，空字符串表示使用 MBTI 预设。"""
    rows = _get("user_profile", {"id": "eq.default_user", "select": "custom_persona"})
    if rows and rows[0].get("custom_persona"):
        return rows[0]["custom_persona"]
    return ""


def save_custom_persona(persona: str) -> None:
    """保存自定义人格描述。"""
    _patch("user_profile", {"id": "eq.default_user"}, {"custom_persona": persona}, return_row=False)


def get_companion_profile() -> dict:
    """一次取出跟宠名字 + 自定义人格，省一次数据库请求。

    返回 {"name": str, "custom_persona": str}
    """
    rows = _get("user_profile", {
        "id": "eq.default_user",
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

def save_chat_message(session_id: str, role: str, content: str) -> None:
    """保存一条聊天消息。"""
    today = now_cn().strftime("%Y-%m-%d")
    _post("chat_session", {
        "session_id": session_id,
        "role": role,
        "content": content,
        "session_date": today,
        "created_at": now_cn().isoformat(),
    }, return_row=False)


def load_session_messages(session_id: str) -> list[dict]:
    """加载指定 session 的所有聊天消息。"""
    rows = _get("chat_session", {
        "session_id": f"eq.{session_id}",
        "select": "role,content",
        "order": "created_at.asc",
    })
    return [{"role": r["role"], "content": r["content"]} for r in rows]


# ---- 精力记录 CRUD ----

def save_energy(energy_level: int, source: str) -> dict:
    """写入一条精力记录，返回写入结果。"""
    now = now_cn().isoformat()
    _post("energy_log", {
        "energy_level": energy_level,
        "source": source,
        "created_at": now,
    }, return_row=False)
    return {"energy_level": energy_level, "source": source, "updated_at": now}


def get_today_energy() -> dict | None:
    """获取今天最新一条精力记录，没有则返回 None。"""
    today_start = now_cn().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    rows = _get("energy_log", {
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


def get_avg_energy_7d() -> float | None:
    """过去 7 天精力均值（每天取最后一条），无数据返回 None。"""
    seven_days_ago = (now_cn() - timedelta(days=7)).isoformat()
    rows = _get("energy_log", {
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

def save_action_log(energy: int, intent: str, strategy: str,
                    recommendation: str, user_action: str) -> None:
    """记录用户对推荐的反馈。"""
    _post("action_log", {
        "energy_at_action": energy,
        "intent": intent,
        "strategy": strategy,
        "recommendation": recommendation,
        "user_action": user_action,
        "timestamp": now_cn().isoformat(),
    }, return_row=False)
