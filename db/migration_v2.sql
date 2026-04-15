-- ═════════════════════════════════════════════════════════════════
-- AI 小管家 v2 多用户建表 + RLS（一次性 migration）
-- 用法：在 Supabase SQL Editor 粘贴整段一次跑完。
-- 项目：ieakiihfsaqqyyjdyjtt.supabase.co
-- 创建于：2026-04-15
--
-- 关键设计：
-- 1. 6 张表都带 user_id UUID，外键到 auth.users，ON DELETE CASCADE
--    （账号删除时所有数据连带清理）
-- 2. 全部启用 RLS + 4 条 CRUD 策略（auth.uid() = user_id）
--    后端用 service_key 仍 bypass RLS（手动加 user_id 过滤），
--    RLS 是 defense-in-depth：万一 anon_key 暴露，挡得住
-- 3. user_profile 用 user_id 作主键（一个 auth user 一条 profile）
-- 4. 其他表用 SERIAL id + user_id 索引
-- 5. handle_new_user trigger：新用户注册时自动建 user_profile
-- 6. chat_session 加 (user_id, session_id) 联合 unique，更稳
-- 7. user_profile 含 deepseek_api_key 字段（第 5 步 BYOK 用，先建着）
-- ═════════════════════════════════════════════════════════════════


-- ─────────────────────────────────────────────
-- 1. user_profile（一个 auth user 一条 profile）
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_profile (
    user_id            UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    nickname           TEXT,
    avg_energy_7d      REAL,
    persona_style      TEXT DEFAULT '温柔型',
    user_memo          TEXT DEFAULT '',
    ai_memo            TEXT DEFAULT '',
    daily_memo         TEXT DEFAULT '{}',
    companion_name     TEXT DEFAULT '小白',
    custom_persona     TEXT DEFAULT '',
    deepseek_api_key   TEXT DEFAULT '',     -- BYOK，第 5 步打磨阶段接入；现在留位
    created_at         TIMESTAMPTZ DEFAULT now()
);


-- ─────────────────────────────────────────────
-- 2. energy_log（精力记录）
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS energy_log (
    id            SERIAL PRIMARY KEY,
    user_id       UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    energy_level  INTEGER NOT NULL CHECK (energy_level BETWEEN 1 AND 5),
    source        TEXT NOT NULL,
    sleep_hours   REAL,
    state_tags    TEXT,
    created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_energy_log_user ON energy_log(user_id, created_at DESC);


-- ─────────────────────────────────────────────
-- 3. action_log（用户行为审计）
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS action_log (
    id                SERIAL PRIMARY KEY,
    user_id           UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    energy_at_action  INTEGER,
    intent            TEXT,
    strategy          TEXT,
    recommendation    TEXT,
    user_action       TEXT NOT NULL,
    timestamp         TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_action_log_user ON action_log(user_id, timestamp DESC);


-- ─────────────────────────────────────────────
-- 4. task（任务）
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS task (
    id              SERIAL PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
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
CREATE INDEX IF NOT EXISTS idx_task_user_status ON task(user_id, status);
CREATE INDEX IF NOT EXISTS idx_task_user_created ON task(user_id, created_at DESC);


-- ─────────────────────────────────────────────
-- 5. recurring_task（循环任务模板）
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS recurring_task (
    id              SERIAL PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    keyword         TEXT NOT NULL,
    task_type       TEXT DEFAULT 'work',
    default_minutes INTEGER,
    active          INTEGER DEFAULT 1,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_recurring_user ON recurring_task(user_id);


-- ─────────────────────────────────────────────
-- 6. chat_session（聊天消息）
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_session (
    id           SERIAL PRIMARY KEY,
    user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    session_id   TEXT NOT NULL,
    role         TEXT NOT NULL,
    content      TEXT NOT NULL,
    session_date TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_session_user ON chat_session(user_id, session_id, created_at);
-- 注：session_id 全局是 UUID 不会撞，无需 (user_id, session_id) 联合 unique；
-- 同一 session 可以有多条消息，所以这里不能 unique，加索引就够了。


-- ═════════════════════════════════════════════════════════════════
-- RLS（Row Level Security）
-- 6 张表全开 + 标准 4 条策略：select/insert/update/delete 限本人
-- ═════════════════════════════════════════════════════════════════

ALTER TABLE user_profile    ENABLE ROW LEVEL SECURITY;
ALTER TABLE energy_log      ENABLE ROW LEVEL SECURITY;
ALTER TABLE action_log      ENABLE ROW LEVEL SECURITY;
ALTER TABLE task            ENABLE ROW LEVEL SECURITY;
ALTER TABLE recurring_task  ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_session    ENABLE ROW LEVEL SECURITY;


-- ─── user_profile 策略（PK 是 user_id 本身） ───
DROP POLICY IF EXISTS up_select ON user_profile;
DROP POLICY IF EXISTS up_insert ON user_profile;
DROP POLICY IF EXISTS up_update ON user_profile;
DROP POLICY IF EXISTS up_delete ON user_profile;

CREATE POLICY up_select ON user_profile FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY up_insert ON user_profile FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY up_update ON user_profile FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY up_delete ON user_profile FOR DELETE USING (auth.uid() = user_id);


-- ─── 其他表通用模板（每张都 4 条） ───
-- energy_log
DROP POLICY IF EXISTS el_select ON energy_log;
DROP POLICY IF EXISTS el_insert ON energy_log;
DROP POLICY IF EXISTS el_update ON energy_log;
DROP POLICY IF EXISTS el_delete ON energy_log;
CREATE POLICY el_select ON energy_log FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY el_insert ON energy_log FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY el_update ON energy_log FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY el_delete ON energy_log FOR DELETE USING (auth.uid() = user_id);

-- action_log
DROP POLICY IF EXISTS al_select ON action_log;
DROP POLICY IF EXISTS al_insert ON action_log;
DROP POLICY IF EXISTS al_update ON action_log;
DROP POLICY IF EXISTS al_delete ON action_log;
CREATE POLICY al_select ON action_log FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY al_insert ON action_log FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY al_update ON action_log FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY al_delete ON action_log FOR DELETE USING (auth.uid() = user_id);

-- task
DROP POLICY IF EXISTS tk_select ON task;
DROP POLICY IF EXISTS tk_insert ON task;
DROP POLICY IF EXISTS tk_update ON task;
DROP POLICY IF EXISTS tk_delete ON task;
CREATE POLICY tk_select ON task FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY tk_insert ON task FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY tk_update ON task FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY tk_delete ON task FOR DELETE USING (auth.uid() = user_id);

-- recurring_task
DROP POLICY IF EXISTS rt_select ON recurring_task;
DROP POLICY IF EXISTS rt_insert ON recurring_task;
DROP POLICY IF EXISTS rt_update ON recurring_task;
DROP POLICY IF EXISTS rt_delete ON recurring_task;
CREATE POLICY rt_select ON recurring_task FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY rt_insert ON recurring_task FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY rt_update ON recurring_task FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY rt_delete ON recurring_task FOR DELETE USING (auth.uid() = user_id);

-- chat_session
DROP POLICY IF EXISTS cs_select ON chat_session;
DROP POLICY IF EXISTS cs_insert ON chat_session;
DROP POLICY IF EXISTS cs_update ON chat_session;
DROP POLICY IF EXISTS cs_delete ON chat_session;
CREATE POLICY cs_select ON chat_session FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY cs_insert ON chat_session FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY cs_update ON chat_session FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY cs_delete ON chat_session FOR DELETE USING (auth.uid() = user_id);


-- ═════════════════════════════════════════════════════════════════
-- Trigger：新用户注册时自动建 user_profile 行
-- 这样前端 Anonymous Auth 一登录，profile 立刻就在
-- ═════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO public.user_profile (user_id)
    VALUES (NEW.id)
    ON CONFLICT (user_id) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();


-- ═════════════════════════════════════════════════════════════════
-- 完成
-- 验证一下：跑下面这句应该返回 6
-- SELECT count(*) FROM information_schema.tables
-- WHERE table_schema = 'public'
--   AND table_name IN ('user_profile','energy_log','action_log','task','recurring_task','chat_session');
-- ═════════════════════════════════════════════════════════════════
