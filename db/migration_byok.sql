-- ═════════════════════════════════════════════════════════════════
-- AI 小管家 BYOK 迁移（2026-04-22）
-- 用户自带 API key，user_profile 加 4 个字段
-- 用法：在 Supabase SQL Editor 粘贴跑一次
-- ═════════════════════════════════════════════════════════════════

ALTER TABLE user_profile
    ADD COLUMN IF NOT EXISTS llm_provider TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS llm_base_url TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS llm_model TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS llm_api_key TEXT DEFAULT '';

-- 验证：
--   SELECT column_name FROM information_schema.columns
--   WHERE table_name = 'user_profile'
--     AND column_name IN ('llm_provider', 'llm_base_url', 'llm_model', 'llm_api_key');
--   → 应该返回 4 行
