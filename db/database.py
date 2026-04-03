"""SQLite 连接与初始化，提供精力相关 CRUD 操作。"""

import sqlite3
import os
from datetime import datetime, timedelta, timezone

# 北京时间 UTC+8
_CN_TZ = timezone(timedelta(hours=8))


def now_cn() -> datetime:
    """返回当前北京时间。"""
    return datetime.now(_CN_TZ)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "butler.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """建表。应用启动时调用一次。"""
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS user_profile (
            id            TEXT PRIMARY KEY,
            nickname      TEXT,
            avg_energy_7d REAL,
            persona_style TEXT DEFAULT '温柔型',
            user_memo     TEXT DEFAULT '',
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS energy_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            energy_level INTEGER NOT NULL CHECK(energy_level BETWEEN 1 AND 5),
            source       TEXT NOT NULL,
            sleep_hours  REAL,
            state_tags   TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS action_log (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            energy_at_action INTEGER,
            intent           TEXT,
            strategy         TEXT,
            recommendation   TEXT,
            user_action      TEXT NOT NULL,
            timestamp        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS task (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword         TEXT NOT NULL,
            combo           TEXT,
            energy_at_start INTEGER,
            status          TEXT NOT NULL DEFAULT 'executing',
            default_minutes INTEGER,
            task_type       TEXT DEFAULT 'work',
            started_at      TIMESTAMP,
            paused_at       TIMESTAMP,
            completed_at    TIMESTAMP,
            scheduled_at    TIMESTAMP,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS recurring_task (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword         TEXT NOT NULL,
            task_type       TEXT DEFAULT 'work',
            default_minutes INTEGER,
            active          INTEGER DEFAULT 1,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_session (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id   TEXT NOT NULL,
            role         TEXT NOT NULL,
            content      TEXT NOT NULL,
            session_date TEXT NOT NULL,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 确保默认用户存在
    c.execute(
        "INSERT OR IGNORE INTO user_profile (id, nickname) VALUES (?, ?)",
        ("default_user", "用户"),
    )

    # 兼容旧表：如果 user_memo 列不存在则添加
    try:
        c.execute("SELECT user_memo FROM user_profile LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE user_profile ADD COLUMN user_memo TEXT DEFAULT ''")

    # 兼容旧表：如果 ai_memo 列不存在则添加
    try:
        c.execute("SELECT ai_memo FROM user_profile LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE user_profile ADD COLUMN ai_memo TEXT DEFAULT ''")

    # 兼容旧表：如果 daily_memo 列不存在则添加
    try:
        c.execute("SELECT daily_memo FROM user_profile LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE user_profile ADD COLUMN daily_memo TEXT DEFAULT '{}'")

    # 兼容旧表：如果 scheduled_at 列不存在则添加
    try:
        c.execute("SELECT scheduled_at FROM task LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE task ADD COLUMN scheduled_at TIMESTAMP")

    # 兼容旧表：如果 detail 列不存在则添加
    try:
        c.execute("SELECT detail FROM task LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE task ADD COLUMN detail TEXT DEFAULT ''")

    conn.commit()
    conn.close()


# ---- user_memo CRUD ----

def get_user_memo() -> str:
    """获取用户记忆库内容。"""
    conn = get_connection()
    row = conn.execute("SELECT user_memo FROM user_profile WHERE id = 'default_user'").fetchone()
    conn.close()
    return row["user_memo"] if row and row["user_memo"] else ""


def save_user_memo(memo: str) -> None:
    """保存用户手记内容。"""
    conn = get_connection()
    conn.execute("UPDATE user_profile SET user_memo = ? WHERE id = 'default_user'", (memo,))
    conn.commit()
    conn.close()


def get_ai_memo() -> str:
    """获取 AI 自动记忆内容。"""
    conn = get_connection()
    row = conn.execute("SELECT ai_memo FROM user_profile WHERE id = 'default_user'").fetchone()
    conn.close()
    return row["ai_memo"] if row and row["ai_memo"] else ""


def save_ai_memo(memo: str) -> None:
    """保存 AI 自动记忆内容。"""
    conn = get_connection()
    conn.execute("UPDATE user_profile SET ai_memo = ? WHERE id = 'default_user'", (memo,))
    conn.commit()
    conn.close()


def clear_ai_memo() -> None:
    """清空 AI 自动记忆。"""
    conn = get_connection()
    conn.execute("UPDATE user_profile SET ai_memo = '' WHERE id = 'default_user'")
    conn.commit()
    conn.close()


def get_daily_memo() -> str:
    """获取每日记忆 JSON 字符串。"""
    conn = get_connection()
    row = conn.execute("SELECT daily_memo FROM user_profile WHERE id = 'default_user'").fetchone()
    conn.close()
    return row["daily_memo"] if row and row["daily_memo"] else "{}"


def save_daily_memo(memo: str) -> None:
    """保存每日记忆 JSON 字符串。"""
    conn = get_connection()
    conn.execute("UPDATE user_profile SET daily_memo = ? WHERE id = 'default_user'", (memo,))
    conn.commit()
    conn.close()


# ---- chat_session CRUD ----

def save_chat_message(session_id: str, role: str, content: str) -> None:
    """保存一条聊天消息。"""
    conn = get_connection()
    today = now_cn().strftime("%Y-%m-%d")
    conn.execute(
        "INSERT INTO chat_session (session_id, role, content, session_date, created_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, role, content, today, now_cn().isoformat()),
    )
    conn.commit()
    conn.close()


def load_session_messages(session_id: str) -> list[dict]:
    """加载指定 session 的所有聊天消息。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT role, content FROM chat_session WHERE session_id = ? ORDER BY created_at",
        (session_id,),
    ).fetchall()
    conn.close()
    return [{"role": row["role"], "content": row["content"]} for row in rows]

# ---- 精力记录 CRUD ----

def save_energy(energy_level: int, source: str) -> dict:
    """写入一条精力记录，返回写入结果。"""
    conn = get_connection()
    now = now_cn().isoformat()
    conn.execute(
        "INSERT INTO energy_log (energy_level, source, created_at) VALUES (?, ?, ?)",
        (energy_level, source, now),
    )
    conn.commit()
    conn.close()
    return {"energy_level": energy_level, "source": source, "updated_at": now}


def get_today_energy() -> dict | None:
    """获取今天最新一条精力记录，没有则返回 None。"""
    conn = get_connection()
    today_start = now_cn().replace(hour=0, minute=0, second=0).isoformat()
    row = conn.execute(
        "SELECT energy_level, source, created_at FROM energy_log "
        "WHERE created_at >= ? ORDER BY created_at DESC LIMIT 1",
        (today_start,),
    ).fetchone()
    conn.close()
    if row:
        return {"energy_level": row["energy_level"], "source": row["source"],
                "updated_at": row["created_at"]}
    return None


def get_avg_energy_7d() -> float | None:
    """过去 7 天精力均值（每天取最后一条），无数据返回 None。"""
    conn = get_connection()
    seven_days_ago = (now_cn() - timedelta(days=7)).isoformat()
    rows = conn.execute(
        "SELECT energy_level, DATE(created_at) as day "
        "FROM energy_log WHERE created_at >= ? "
        "ORDER BY created_at DESC",
        (seven_days_ago,),
    ).fetchall()
    conn.close()

    if not rows:
        return None

    # 每天只取最新的一条
    daily = {}
    for r in rows:
        day = r["day"]
        if day not in daily:
            daily[day] = r["energy_level"]

    return sum(daily.values()) / len(daily)


# ---- action_log CRUD ----

def save_action_log(energy: int, intent: str, strategy: str,
                    recommendation: str, user_action: str) -> None:
    """记录用户对推荐的反馈（开始/换一个/不要）。"""
    conn = get_connection()
    conn.execute(
        "INSERT INTO action_log (energy_at_action, intent, strategy, recommendation, user_action, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (energy, intent, strategy, recommendation, user_action, now_cn().isoformat()),
    )
    conn.commit()
    conn.close()
