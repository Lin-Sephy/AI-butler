/**
 * 全局 Auth Context。
 *
 * 行为：
 * - 首次打开（无 session）→ 自动 signInAnonymously()，Supabase 建匿名 auth.users 行
 *   → handle_new_user trigger 自动建 user_profile 行
 * - 已有 session → 沿用，autoRefresh 处理 token 过期
 * - 监听 auth 状态变化（登录/登出/token 刷新），保持 React state 同步
 *
 * 用法：
 *   const { user, session, loading } = useAuth()
 *   if (loading) return <Loading />
 *   if (!user) return <Loading />  // 自动匿名登录中
 *   return <App user={user} />
 */

import { createContext, useContext, useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null)
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function bootstrap() {
      try {
        // 1. 看是否已有保存的 session
        const { data: { session: existing } } = await supabase.auth.getSession()
        if (cancelled) return

        if (existing) {
          setSession(existing)
          setUser(existing.user)
          setLoading(false)
          return
        }

        // 2. 没有 session → 自动匿名登录
        const { data, error: signInError } = await supabase.auth.signInAnonymously()
        if (cancelled) return

        if (signInError) {
          // 常见原因：Supabase 项目没启用 Anonymous Sign-Ins
          // Dashboard → Authentication → Providers → Anonymous Sign-Ins → Enable
          throw signInError
        }

        setSession(data.session)
        setUser(data.user)
      } catch (e) {
        if (!cancelled) setError(e)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    bootstrap()

    // 监听后续 auth 变化（token 刷新、登出等）
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, newSession) => {
        if (cancelled) return
        setSession(newSession)
        setUser(newSession?.user ?? null)
      }
    )

    return () => {
      cancelled = true
      subscription.unsubscribe()
    }
  }, [])

  return (
    <AuthContext.Provider value={{ user, session, loading, error }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
