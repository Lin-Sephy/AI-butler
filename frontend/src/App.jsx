/**
 * AI 身体状态计划管家 — v2 Web App
 *
 * 第 1 步：任务面板 + 全屏专注遮罩。
 * 聊天/数据/我的 仍为占位骨架，第 2-5 步做。
 */

import { useState, useEffect } from 'react'
import { useAuth } from './contexts/AuthContext.jsx'
import { ToastProvider } from './contexts/ToastContext.jsx'
import TasksPage from './pages/TasksPage.jsx'
import ChatPage from './pages/ChatPage.jsx'
import StatsPage from './pages/StatsPage.jsx'
import MePage from './pages/MePage.jsx'

const TABS = [
  { key: 'tasks',  label: '任务' },
  { key: 'chat',   label: '聊天' },
  { key: 'stats',  label: '数据' },
  { key: 'me',     label: '我的' },
]

const WAKE_MESSAGES = [
  '正在唤醒小白……',
  '小白好像在睡觉，再等等...',
  '服务器刚睡醒正在洗脸...',
]

export default function App() {
  const { user, loading, error } = useAuth()
  const [tab, setTab] = useState('tasks')
  const [wakeStage, setWakeStage] = useState(0)

  useEffect(() => {
    if (!loading) { setWakeStage(0); return }
    const t1 = setTimeout(() => setWakeStage(1), 5000)
    const t2 = setTimeout(() => setWakeStage(2), 15000)
    return () => { clearTimeout(t1); clearTimeout(t2) }
  }, [loading])

  if (loading) {
    return <CenterMessage>{WAKE_MESSAGES[wakeStage]}</CenterMessage>
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
    <ToastProvider>
      <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        <main style={{ flex: 1, padding: '40px 24px', maxWidth: 720, margin: '0 auto', width: '100%' }}>
          {tab === 'tasks' && <TasksPage />}
          {tab === 'chat'  && <ChatPage />}
          {tab === 'stats' && <StatsPage />}
          {tab === 'me'    && <MePage />}
        </main>
        <TabBar current={tab} onChange={setTab} />
      </div>
    </ToastProvider>
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
      fontSize: 14,
    }}>
      {children}
    </div>
  )
}
