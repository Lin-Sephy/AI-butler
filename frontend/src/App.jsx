/**
 * AI 身体状态计划管家 — v2 Web App
 *
 * 第 1 步：任务面板 + 全屏专注遮罩。
 * 聊天/数据/我的 仍为占位骨架，第 2-5 步做。
 */

import { useState } from 'react'
import { useAuth } from './contexts/AuthContext.jsx'
import TasksPage from './pages/TasksPage.jsx'
import ChatPage from './pages/ChatPage.jsx'

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
        {tab === 'tasks' && <TasksPage />}
        {tab === 'chat'  && <ChatPage />}
        {tab === 'stats' && <Placeholder title="数据" />}
        {tab === 'me'    && <Placeholder title="我的" />}
      </main>
      <TabBar current={tab} onChange={setTab} />
    </div>
  )
}

function Placeholder({ title }) {
  return (
    <div>
      <h1 style={{ fontSize: 28, fontWeight: 400, marginBottom: 8 }}>{title}</h1>
      <p style={{ color: 'var(--color-subtle)' }}>
        骨架占位 · 后续步骤实现
      </p>
    </div>
  )
}

function TabBar({ current, onChange }) {
  return (
    <nav style={{
      display: 'flex', justifyContent: 'space-around',
      background: 'var(--color-surface)',
      borderTop: '1px solid var(--color-line)',
      padding: '12px 0',
    }}>
      {TABS.map(t => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          style={{
            background: 'transparent', border: 'none',
            color: current === t.key ? 'var(--color-primary)' : 'var(--color-subtle)',
            fontFamily: 'inherit', fontSize: 14,
            cursor: 'pointer', padding: '6px 16px',
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
    <div style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      padding: 24, textAlign: 'center',
      color: 'var(--color-subtle)',
    }}>
      {children}
    </div>
  )
}
