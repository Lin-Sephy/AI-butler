-- 2026-06-18 lightweight chat trace
-- 用于排查每轮聊天的模式、上下文注入、模型/工具结果和最终回复。
-- 注意：trace 只存摘要/截断内容，不作为完整聊天历史。

CREATE TABLE IF NOT EXISTS chat_trace (
  id BIGSERIAL PRIMARY KEY,
  trace_id TEXT NOT NULL UNIQUE,
  user_id UUID NOT NULL,
  session_id TEXT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'chat',
  status TEXT NOT NULL DEFAULT 'success',
  message_excerpt TEXT,
  context_json JSONB DEFAULT '{}'::jsonb,
  model_json JSONB DEFAULT '{}'::jsonb,
  tool_calls_json JSONB DEFAULT '[]'::jsonb,
  response_excerpt TEXT,
  result_json JSONB DEFAULT '{}'::jsonb,
  error_message TEXT,
  latency_ms INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_trace_user_time
  ON chat_trace(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_trace_session_time
  ON chat_trace(user_id, session_id, created_at DESC);

ALTER TABLE chat_trace ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ct_select ON chat_trace;
DROP POLICY IF EXISTS ct_insert ON chat_trace;
DROP POLICY IF EXISTS ct_update ON chat_trace;
DROP POLICY IF EXISTS ct_delete ON chat_trace;

CREATE POLICY ct_select ON chat_trace FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY ct_insert ON chat_trace FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY ct_update ON chat_trace FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY ct_delete ON chat_trace FOR DELETE USING (auth.uid() = user_id);
