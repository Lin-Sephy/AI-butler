-- AI 小管家 Supabase 建表（从 SQLite 迁移）
-- 在 Supabase SQL Editor 中运行此文件

CREATE TABLE IF NOT EXISTS user_profile (
    id            TEXT PRIMARY KEY,
    nickname      TEXT,
    avg_energy_7d REAL,
    persona_style TEXT DEFAULT '温柔型',
    user_memo     TEXT DEFAULT '',
    ai_memo       TEXT DEFAULT '',
    daily_memo    TEXT DEFAULT '{}',
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS energy_log (
    id           SERIAL PRIMARY KEY,
    energy_level INTEGER NOT NULL CHECK(energy_level BETWEEN 1 AND 5),
    source       TEXT NOT NULL,
    sleep_hours  REAL,
    state_tags   TEXT,
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS action_log (
    id               SERIAL PRIMARY KEY,
    energy_at_action INTEGER,
    intent           TEXT,
    strategy         TEXT,
    recommendation   TEXT,
    user_action      TEXT NOT NULL,
    timestamp        TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS task (
    id              SERIAL PRIMARY KEY,
    keyword         TEXT NOT NULL,
    combo           TEXT,
    energy_at_start INTEGER,
    status          TEXT NOT NULL DEFAULT 'executing',
    default_minutes INTEGER,
    task_type       TEXT DEFAULT 'work',
    detail          TEXT DEFAULT '',
    started_at      TIMESTAMPTZ,
    paused_at       TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    scheduled_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recurring_task (
    id              SERIAL PRIMARY KEY,
    keyword         TEXT NOT NULL,
    task_type       TEXT DEFAULT 'work',
    default_minutes INTEGER,
    active          INTEGER DEFAULT 1,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_session (
    id           SERIAL PRIMARY KEY,
    session_id   TEXT NOT NULL,
    role         TEXT NOT NULL,
    content      TEXT NOT NULL,
    session_date TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT now()
);

-- 插入默认用户
INSERT INTO user_profile (id, nickname)
VALUES ('default_user', '用户')
ON CONFLICT (id) DO NOTHING;
