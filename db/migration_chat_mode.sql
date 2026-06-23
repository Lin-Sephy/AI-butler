-- 2026-04-23 chat_session 加 mode 字段 · 闲聊 / 计划模式分流
--
-- 背景：闲聊模式和计划模式共用一个 session_id，历史混在一起，导致 DS
-- 在闲聊模式下看到以前 query_tasks 的结果，产生"你有个午休吃饭任务"这种
-- 幻觉。
--
-- 方案：每条消息加 mode 标签；拉历史给 DS 时按当前 mode 过滤，UI 展示
-- 仍全部显示但穿插"---任务模式---/---闲聊模式---"分隔符。
--
-- 老数据 mode 默认为 NULL，应用层把 NULL 视作 'chat'（因为闲聊用得更多，
-- 且老数据量小——目前全部只有两天）

ALTER TABLE chat_session ADD COLUMN IF NOT EXISTS mode TEXT;

-- 不加 NOT NULL 也不加 CHECK，让老数据 NULL 共存；应用层保证新写入的
-- 消息永远带明确的 mode ('chat' 或 'plan')
