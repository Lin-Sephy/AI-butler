-- 给 user_profile 表添加 companion_name 和 custom_persona 字段
-- 在 Supabase SQL Editor 中运行

ALTER TABLE user_profile
ADD COLUMN IF NOT EXISTS companion_name TEXT DEFAULT '小白';

ALTER TABLE user_profile
ADD COLUMN IF NOT EXISTS custom_persona TEXT DEFAULT '';

-- 给已有的 default_user 设置默认值（万一原本是 NULL）
UPDATE user_profile
SET companion_name = '小白'
WHERE id = 'default_user' AND (companion_name IS NULL OR companion_name = '');

UPDATE user_profile
SET custom_persona = ''
WHERE id = 'default_user' AND custom_persona IS NULL;
