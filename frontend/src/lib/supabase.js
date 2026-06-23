/**
 * Supabase client 单例。
 *
 * 用 publishable/anon key（前端可以暴露），配合数据库 RLS 是安全的。
 * 不要在前端用 service_key（那个 bypass RLS）。
 */

import { createClient } from '@supabase/supabase-js'

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  throw new Error(
    '缺少 Supabase 环境变量。请复制 frontend/.env.example 为 .env.local 并填值。'
  )
}

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    persistSession: true,    // 保存到 localStorage，刷新不丢登录
    autoRefreshToken: true,  // access_token 快过期前自动刷新
    detectSessionInUrl: false, // 不靠 magic link 回调（v2 走匿名+邮箱绑定）
  },
})
