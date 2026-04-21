-- ═════════════════════════════════════════════════════════════════
-- AI 小管家 v5.0 迁移：project 表 + task 加 project_id + daily_routine
-- 用法：在 Supabase SQL Editor 粘贴整段一次跑完
-- 项目：ieakiihfsaqqyyjdyjtt.supabase.co
-- 创建于：2026-04-20
--
-- 改动：
-- 1. user_profile 加 daily_routine（用户的日常作息文本）
-- 2. task 加 project_id（可选的项目归属，外键到 project.id）
--    task_type 现在接受 'work' / 'rest' / 'event' 三种值（应用层校验，DB 不加 CHECK 保留灵活性）
-- 3. 新增 project 表（长期项目 + 摘要 + 关键词）+ RLS + updated_at trigger
-- ═════════════════════════════════════════════════════════════════


-- ─────────────────────────────────────────────
-- 1. user_profile 加 daily_routine
-- ─────────────────────────────────────────────
ALTER TABLE user_profile
    ADD COLUMN IF NOT EXISTS daily_routine TEXT DEFAULT '';


-- ─────────────────────────────────────────────
-- 2. 新建 project 表
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS project (
    id          SERIAL PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    keywords    TEXT[] NOT NULL DEFAULT '{}',   -- 用于自动匹配 task
    summary     TEXT DEFAULT '',                 -- LLM 覆盖更新
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_project_user ON project(user_id, updated_at DESC);


-- ─────────────────────────────────────────────
-- 3. task 表加 project_id（nullable，老数据不影响）
-- ─────────────────────────────────────────────
ALTER TABLE task
    ADD COLUMN IF NOT EXISTS project_id INTEGER REFERENCES project(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_task_project ON task(project_id) WHERE project_id IS NOT NULL;


-- ─────────────────────────────────────────────
-- 4. project 表的 RLS
-- ─────────────────────────────────────────────
ALTER TABLE project ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pj_select ON project;
DROP POLICY IF EXISTS pj_insert ON project;
DROP POLICY IF EXISTS pj_update ON project;
DROP POLICY IF EXISTS pj_delete ON project;

CREATE POLICY pj_select ON project FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY pj_insert ON project FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY pj_update ON project FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY pj_delete ON project FOR DELETE USING (auth.uid() = user_id);


-- ─────────────────────────────────────────────
-- 5. project.updated_at 自动更新 trigger
-- ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION touch_project_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_project_updated_at ON project;
CREATE TRIGGER trg_project_updated_at
    BEFORE UPDATE ON project
    FOR EACH ROW
    EXECUTE FUNCTION touch_project_updated_at();


-- ═════════════════════════════════════════════════════════════════
-- 完成
-- 验证：
--   SELECT column_name FROM information_schema.columns
--   WHERE table_name = 'user_profile' AND column_name = 'daily_routine';
--   → 应该返回 1 行
--
--   SELECT column_name FROM information_schema.columns
--   WHERE table_name = 'task' AND column_name = 'project_id';
--   → 应该返回 1 行
--
--   SELECT table_name FROM information_schema.tables
--   WHERE table_schema = 'public' AND table_name = 'project';
--   → 应该返回 1 行
-- ═════════════════════════════════════════════════════════════════
