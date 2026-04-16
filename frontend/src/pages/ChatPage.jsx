/**
 * 聊天页（双 mode layout）。
 *
 * - idle mode（闲玩）：白鼬全身居中（占位，第 3 步画完整）+ 输入框暂存。无消息流。
 * - chat mode：白鼬半身趴顶 + 消息流 + 顶栏（<<退出 / ⊕新建对话 / ⚙️设置）
 *
 * 切换触发：
 *   idle → chat：用户发送第一条消息（不是打字）
 *   chat → idle：点 << 退出键
 *   ⊕ 新建对话：清空消息历史，留在 chat mode（messages 为空）
 *
 * 数据来源：useChat() 提供 messages/send/record/dismissRec/resetSession/pendingTaskRec
 */

import { useState, useEffect, useRef } from 'react'
import { useChat } from '../contexts/ChatContext.jsx'
import StoatHalf from '../components/StoatHalf.jsx'
import ChatBubble from '../components/ChatBubble.jsx'

export default function ChatPage() {
  const {
    messages, loading, error,
    pendingTaskRec, send, record, dismissRec, resetSession,
  } = useChat()

  // mode 是纯视觉态：进入时若已有历史 → chat mode，否则 idle mode
  const [mode, setMode] = useState(messages.length > 0 ? 'chat' : 'idle')
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const messagesEndRef = useRef(null)

  // 历史 load 完成后若有消息要切到 chat
  useEffect(() => {
    if (messages.length > 0 && mode === 'idle') setMode('chat')
  }, [messages.length])

  // 新消息自动滚到底
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSend(e) {
    e?.preventDefault()
    const text = input.trim()
    if (!text || sending) return
    setSending(true)
    setMode('chat')   // 发送即切 chat mode
    setInput('')
    try {
      await send(text)
    } finally {
      setSending(false)
    }
  }

  function handleExitChat() {
    setMode('idle')
  }

  async function handleNewSession() {
    await resetSession()
    // 留在 chat mode，messages 已被 resetSession 清空
  }

  if (loading) {
    return <CenterText>正在唤醒小白……</CenterText>
  }

  // 计算 stoat 状态：sending 时 thinking；用户在打字时 listening；否则 idle
  const stoatState = sending ? 'thinking' : (input.length > 0 ? 'listening' : 'idle')

  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      // 撑满 main 容器的高度，main 已经处理了 padding 与 max-width
      minHeight: 'calc(100vh - 60px - 80px)',  // 减底部 tab + main 上下 padding
      // 把 padding 还原成边到边，方便顶栏/输入框拉满
      margin: '-40px -24px',
    }}>

      {/* ─── 顶栏（chat mode 时白鼬坐在分隔线上） ─── */}
      <header style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end',
        padding: '14px 20px',
        height: mode === 'chat' ? 140 : 56,   // chat mode 留高让白鼬探出
        borderBottom: '1px solid var(--color-line)',
        background: 'var(--color-base)',
        position: 'sticky', top: 0, zIndex: 10,
      }}>
        {/* 左：退出（仅 chat mode） */}
        <div style={{ minWidth: 60, alignSelf: 'center' }}>
          {mode === 'chat' && (
            <IconBtn title="退出闲玩" onClick={handleExitChat}>
              <span style={{ fontSize: 18, lineHeight: 1 }}>‹‹</span>
            </IconBtn>
          )}
        </div>

        {/* 中：chat mode = 白鼬坐分隔线上；idle mode = 提示文字 */}
        <div style={{
          flex: 1,
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'flex-end',
          alignSelf: 'stretch',
          position: 'relative',
        }}>
          {mode === 'chat' ? (
            <div style={{
              position: 'absolute',
              bottom: -1,            // 让底边正好压在 1px 分隔线上
              left: '50%',
              transform: 'translateX(-50%)',
              lineHeight: 0,
            }}>
              <StoatHalf view="half" state={stoatState} width={180} />
            </div>
          ) : (
            <div style={{ fontSize: 14, color: 'var(--color-subtle)' }}>
              小白在等你
            </div>
          )}
        </div>

        {/* 右：⊕ + ⚙️ */}
        <div style={{ display: 'flex', gap: 4, minWidth: 60, justifyContent: 'flex-end', alignSelf: 'center' }}>
          {mode === 'chat' && (
            <IconBtn title="新建对话" onClick={handleNewSession}>
              <CirclePlus />
            </IconBtn>
          )}
          <IconBtn title="设置" onClick={() => alert('设置面板待第 4-5 步做')}>
            <Gear />
          </IconBtn>
        </div>
      </header>

      {/* ─── 主区 ─── */}
      <main style={{
        flex: 1,
        overflowY: 'auto',
        padding: '20px 20px 0',
        display: 'flex', flexDirection: 'column',
        position: 'relative',
        background: 'var(--color-base)',
      }}>
        {/* 针叶暗纹背景层 */}
        <div style={{
          position: 'absolute', inset: 0, pointerEvents: 'none',
          opacity: 0.06,
          backgroundRepeat: 'repeat',
          backgroundSize: '360px 240px',
          backgroundImage: `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='360' height='240' viewBox='0 0 360 240'><g fill='%234896c4' opacity='0.45'><path d='M40 200 L30 160 L50 160 Z M35 170 L25 130 L45 130 Z M37 140 L28 100 L46 100 Z'/><path d='M140 210 L128 170 L152 170 Z M134 180 L124 140 L144 140 Z'/><path d='M260 200 L248 160 L272 160 Z M254 170 L244 130 L264 130 Z M256 140 L247 100 L265 100 Z M258 110 L250 80 L266 80 Z'/><path d='M340 205 L330 170 L350 170 Z M335 180 L325 145 L345 145 Z'/></g></svg>")`,
        }} />

        {error && (
          <div style={{
            padding: '10px 14px', marginBottom: 12,
            borderRadius: 'var(--radius)',
            background: '#fee', border: '1px solid #fbb',
            fontSize: 13, color: '#933',
            position: 'relative', zIndex: 1,
          }}>
            {error}
          </div>
        )}

        {mode === 'idle' ? (
          <IdleView />
        ) : (
          <ChatView
            messages={messages}
            pendingTaskRec={pendingTaskRec}
            onRecord={record}
            onDismiss={dismissRec}
            messagesEndRef={messagesEndRef}
          />
        )}
      </main>

      {/* ─── 输入框（始终在底） ─── */}
      <form onSubmit={handleSend} style={{
        display: 'flex', gap: 8, padding: '12px 20px',
        borderTop: '1px solid var(--color-line)',
        background: 'var(--color-surface)',
      }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder={mode === 'idle' ? '跟小白说点什么...' : '...'}
          disabled={sending}
          style={{
            flex: 1, padding: '10px 14px',
            borderRadius: 'var(--radius)',
            border: '1px solid var(--color-line)',
            background: 'var(--color-base)',
            font: 'inherit', color: 'var(--color-text)',
            outline: 'none',
          }}
        />
        <button
          type="submit"
          disabled={!input.trim() || sending}
          style={{
            padding: '10px 20px',
            borderRadius: 'var(--radius)',
            border: '1px solid var(--color-primary)',
            background: input.trim() && !sending ? 'var(--color-primary)' : 'transparent',
            color: input.trim() && !sending ? '#fff' : 'var(--color-subtle)',
            fontSize: 14, fontFamily: 'inherit',
            cursor: !input.trim() || sending ? 'not-allowed' : 'pointer',
          }}
        >
          {sending ? '...' : '发送'}
        </button>
      </form>
    </div>
  )
}

// ─── 闲玩 mode ───
function IdleView() {
  return (
    <div style={{
      flex: 1,
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      gap: 16, position: 'relative', zIndex: 1,
    }}>
      <StoatHalf view="full" state="idle" width={180} />
      <p style={{
        fontSize: 14, color: 'var(--color-subtle)',
        marginTop: 24,
      }}>
        想说什么就说，发出去就开始聊
      </p>
    </div>
  )
}

// ─── 聊天 mode ───
function ChatView({ messages, pendingTaskRec, onRecord, onDismiss, messagesEndRef }) {
  return (
    <>
      {/* 白鼬已挪到 header 中坐在分隔线上，这里只渲染消息流 */}
      <div style={{ position: 'relative', zIndex: 1, paddingBottom: 12, paddingTop: 8 }}>
        {messages.map((m, i) => {
          // 最后一条 AI 消息且当前有 pendingTaskRec → 在该消息下显示按钮
          const isLastAi =
            !!pendingTaskRec &&
            m.role === 'assistant' &&
            i === messages.length - 1
          return (
            <ChatBubble
              key={i}
              message={m}
              taskRec={isLastAi ? pendingTaskRec : null}
              onRecord={onRecord}
              onDismiss={onDismiss}
            />
          )
        })}
        <div ref={messagesEndRef} />
      </div>
    </>
  )
}

// ─── 工具组件 ───

function IconBtn({ children, onClick, title }) {
  return (
    <button
      onClick={onClick}
      title={title}
      style={{
        width: 36, height: 36,
        background: 'transparent', border: 'none',
        borderRadius: 8,
        cursor: 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: 'var(--color-subtle)',
        fontFamily: 'inherit',
        transition: 'background var(--transition) ease-out',
      }}
      onMouseEnter={e => e.currentTarget.style.background = 'var(--color-accent-soft)'}
      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
    >
      {children}
    </button>
  )
}

function CirclePlus() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.4" />
      <line x1="10" y1="6" x2="10" y2="14" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <line x1="6" y1="10" x2="14" y2="10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  )
}

function Gear() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.4" />
      <path
        d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function CenterText({ children }) {
  return (
    <div style={{
      padding: '80px 0', textAlign: 'center',
      color: 'var(--color-subtle)',
    }}>
      {children}
    </div>
  )
}
