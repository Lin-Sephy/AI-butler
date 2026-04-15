/**
 * AI 身体状态计划管家 — v2 Web App
 *
 * 第 0 步骨架：4 tab 占位 + Auth 接通验证 + design tokens 生效。
 * 没有业务，只证明：
 * - 进入 → 自动匿名登录 → 拿到 user_id
 * - 切 tab 不丢 state（auth 跨 tab 共享）
 * - 雪地底 + IBM Plex Serif 字体生效（design tokens）
 *
 * 真业务在第 1 步及之后实现。历史 v0.3 像素空间见 git tag pixel-v0.3。
 */

import { useState } from 'react'
import { useAuth } from './contexts/AuthContext.jsx'
import { apiFetch } from './lib/api.js'

const TABS = [
  { key: 'tasks',  label: '任务' },
  { key: 'chat',   label: '聊天' },
  { key: 'stats',  label: '数据' },
  { key: 'me',     label: '我的' },
]

export default function App() {
  const { user, loading, error } = useAuth()
  const [tab, setTab] = useState('tasks')

  if (loading) {
    return <CenterMessage>正在唤醒小白……</CenterMessage>
  }

  if (error) {
    return (
      <CenterMessage>
        <strong>登录失败</strong>
        <pre style={{ fontSize: 12, marginTop: 12, maxWidth: 480, whiteSpace: 'pre-wrap' }}>
          {error.message}
        </pre>
        <p style={{ fontSize: 13, marginTop: 12, color: 'var(--color-subtle)' }}>
          检查 Supabase Dashboard → Authentication → Providers → Anonymous Sign-Ins 是否启用
        </p>
      </CenterMessage>
    )
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <main style={{ flex: 1, padding: '40px 24px', maxWidth: 720, margin: '0 auto', width: '100%' }}>
        {tab === 'tasks' && <TabPlaceholder title="任务" user={user} />}
        {tab === 'chat'  && <TabPlaceholder title="聊天" user={user} />}
        {tab === 'stats' && <TabPlaceholder title="数据" user={user} />}
        {tab === 'me'    && <TabPlaceholder title="我的" user={user} />}
      </main>
      <TabBar current={tab} onChange={setTab} />
    </div>
  )
}

function TabPlaceholder({ title, user }) {
  const [pingResult, setPingResult] = useState(null)
  const [pinging, setPinging] = useState(false)

  async function pingBackend() {
    setPinging(true)
    setPingResult(null)
    try {
      const data = await apiFetch('/api/tasks/today')
      setPingResult({ ok: true, data })
    } catch (e) {
      setPingResult({ ok: false, error: e.message })
    } finally {
      setPinging(false)
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: 28, fontWeight: 400, marginBottom: 8 }}>{title}</h1>
      <p style={{ color: 'var(--color-subtle)', fontStyle: 'italic', marginBottom: 24 }}>
        骨架占位 · 业务在后续步骤实现
      </p>

      <div
        style={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-line)',
          borderRadius: 'var(--radius)',
          padding: '20px 24px',
          fontSize: 13,
          fontFamily: "'Inter', system-ui, sans-serif",
          marginBottom: 16,
        }}
      >
        <div style={{ marginBottom: 6 }}>
          <span style={{ color: 'var(--color-subtle)' }}>当前 user_id：</span>
        </div>
        <code style={{ fontSize: 12, wordBreak: 'break-all' }}>{user?.id || '(无)'}</code>
        <div style={{ marginTop: 10, color: 'var(--color-subtle)', fontSize: 11 }}>
          匿名 · {user?.is_anonymous ? 'is_anonymous=true' : 'is_anonymous=false'}
        </div>
      </div>

      <button
        onClick={pingBackend}
        disabled={pinging}
        style={{
          padding: '10px 20px',
          borderRadius: 'var(--radius)',
          border: '1px solid var(--color-primary)',
          background: pinging ? 'var(--color-accent-soft)' : 'var(--color-primary)',
          color: pinging ? 'var(--color-primary)' : '#fff',
          fontFamily: 'inherit',
          fontSize: 14,
          cursor: pinging ? 'wait' : 'pointer',
        }}
      >
        {pinging ? '调用中…(冷启动可能 30 秒)' : '调一下后端 /api/tasks/today'}
      </button>

      {pingResult && (
        <pre
          style={{
            marginTop: 16,
            padding: '12px 16px',
            background: pingResult.ok ? 'var(--color-accent-soft)' : '#fee',
            border: '1px solid ' + (pingResult.ok ? 'var(--color-accent)' : '#fbb'),
            borderRadius: 'var(--radius)',
            fontSize: 12,
            fontFamily: "'Inter', monospace, sans-serif",
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
          }}
        >
          {pingResult.ok
            ? JSON.stringify(pingResult.data, null, 2)
            : pingResult.error}
        </pre>
      )}
    </div>
  )
}

function TabBar({ current, onChange }) {
  return (
    <nav
      style={{
        display: 'flex',
        justifyContent: 'space-around',
        background: 'var(--color-surface)',
        borderTop: '1px solid var(--color-line)',
        padding: '12px 0',
      }}
    >
      {TABS.map(t => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          style={{
            background: 'transparent',
            border: 'none',
            color: current === t.key ? 'var(--color-primary)' : 'var(--color-subtle)',
            fontFamily: 'inherit',
            fontSize: 14,
            cursor: 'pointer',
            padding: '6px 16px',
          }}
        >
          {t.label}
        </button>
      ))}
    </nav>
  )
}

function CenterMessage({ children }) {
  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
        textAlign: 'center',
        color: 'var(--color-subtle)',
        fontStyle: 'italic',
      }}
    >
      {children}
    </div>
  )
}
