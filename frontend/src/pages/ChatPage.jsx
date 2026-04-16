/**
 * 聊天页 v2 漫画气泡布局：
 *
 *   - 白鼬永远居中超大，可点逗（状态动效永远活着）
 *   - 顶气泡：小白最新一句，泡尾下指白鼬
 *   - 底气泡：你最新一句，泡尾上指白鼬
 *   - 任务推荐按钮：紧贴 AI 气泡下方独立一行
 *   - 想看完整对话：右上角 📃 切到历史滚动列表视图
 *
 * 数据：useChat() 提供 messages/send/record/dismissRec/resetSession/pendingTaskRec
 */

import { useState, useRef, useEffect } from 'react'
import { useChat } from '../contexts/ChatContext.jsx'
import StoatHalf from '../components/StoatHalf.jsx'
import ChatBubble from '../components/ChatBubble.jsx'

const STOAT_WIDTH = 220
const BUBBLE_MAX_LEN = 100   // 超过截断 + "更多"

export default function ChatPage() {
  const {
    messages, loading, error,
    pendingTaskRec, send, record, dismissRec, resetSession,
  } = useChat()

  const [view, setView] = useState('main')   // 'main' | 'history'
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)

  async function handleSend(e) {
    e?.preventDefault()
    const text = input.trim()
    if (!text || sending) return
    setSending(true)
    setInput('')
    try {
      await send(text)
    } finally {
      setSending(false)
    }
  }

  if (loading) return <CenterText>正在唤醒小白……</CenterText>

  // 历史视图
  if (view === 'history') {
    return (
      <HistoryView
        messages={messages}
        onBack={() => setView('main')}
        onNewSession={resetSession}
        error={error}
      />
    )
  }

  // 小白：最新一条（保留泡尾居中）；你：最近 4 条堆叠右对齐淡化
  const latestAi   = [...messages].reverse().find(m => m.role === 'assistant')
  const recentUsers = messages.filter(m => m.role === 'user').slice(-4)
  const USER_OPACITY = [0.15, 0.35, 0.65, 1]   // 最老 → 最新

  // 白鼬状态：sending 时 thinking；用户在输入框打字时 listening；否则 idle
  const stoatState = sending ? 'thinking' : (input.length > 0 ? 'listening' : 'idle')

  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      minHeight: 'calc(100vh - 60px - 80px)',
      margin: '-40px -24px',
    }}>

      {/* ─── 顶栏极简 ─── */}
      <header style={{
        display: 'flex', justifyContent: 'flex-end', alignItems: 'center',
        padding: '12px 20px',
        background: 'var(--color-base)',
        position: 'sticky', top: 0, zIndex: 10,
        gap: 4,
      }}>
        <IconBtn title="历史对话" onClick={() => setView('history')}>
          <HistoryIcon />
        </IconBtn>
        <IconBtn title="新建对话" onClick={() => {
          if (window.confirm('清空当前对话开新的？')) resetSession()
        }}>
          <CirclePlus />
        </IconBtn>
        <IconBtn title="设置" onClick={() => alert('设置面板待第 4-5 步做')}>
          <Gear />
        </IconBtn>
      </header>

      {/* ─── 主舞台 ─── */}
      <main style={{
        flex: 1,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        padding: '20px 20px 0',
        position: 'relative',
        background: 'var(--color-base)',
        gap: 12,
      }}>
        {/* 针叶背景 */}
        <BgPineLayer />

        {error && (
          <ErrorBanner>{error}</ErrorBanner>
        )}

        {/* 顶气泡：小白说 —— 思考时藏掉，让头顶 3 点泡泡当唯一焦点 */}
        {!sending && latestAi && (
          <SpeechBubble who="ai" text={latestAi.content} />
        )}

        {/* 任务推荐按钮 —— 思考时也藏（按钮属于"上一条 AI 回复"，等新回复来了再说） */}
        {!sending && pendingTaskRec && (
          <TaskActionRow
            keyword={pendingTaskRec.task_keyword}
            minutes={pendingTaskRec.suggested_minutes}
            onRecord={record}
            onDismiss={dismissRec}
          />
        )}

        {/* 白鼬居中 */}
        <div style={{ position: 'relative', zIndex: 1 }}>
          <StoatHalf view="full" state={stoatState} width={STOAT_WIDTH} />
        </div>

        {/* 空状态（无任何消息时） */}
        {!latestAi && recentUsers.length === 0 && (
          <p style={{
            fontSize: 13, color: 'var(--color-subtle)',
            position: 'relative', zIndex: 1,
            marginTop: 16,
          }}>
            说点什么，小白会答你
          </p>
        )}

        {/* 你说：堆叠右对齐贴底，新在底老在顶，opacity 渐弱 */}
        {recentUsers.length > 0 && (
          <div style={{
            position: 'absolute',
            right: 20, bottom: 16,
            display: 'flex', flexDirection: 'column', gap: 6,
            alignItems: 'flex-end',
            zIndex: 2,
            maxWidth: '70%',
          }}>
            {recentUsers.map((m, i) => {
              const ageIndex = recentUsers.length - 1 - i   // 0 = 最新
              const opacity = USER_OPACITY[USER_OPACITY.length - 1 - ageIndex] ?? 0.1
              return (
                <UserBubble key={`u-${messages.length - recentUsers.length + i}`} text={m.content} opacity={opacity} />
              )
            })}
          </div>
        )}
      </main>

      {/* ─── 底输入框 ─── */}
      <form onSubmit={handleSend} style={{
        display: 'flex', gap: 8, padding: '12px 20px',
        borderTop: '1px solid var(--color-line)',
        background: 'var(--color-surface)',
      }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="跟小白说点什么..."
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


// ════════════ 历史视图 ════════════

function HistoryView({ messages, onBack, onNewSession, error }) {
  const endRef = useRef(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      minHeight: 'calc(100vh - 60px - 80px)',
      margin: '-40px -24px',
    }}>
      <header style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '12px 20px',
        borderBottom: '1px solid var(--color-line)',
        background: 'var(--color-base)',
        position: 'sticky', top: 0, zIndex: 10,
      }}>
        <IconBtn title="返回" onClick={onBack}>
          <span style={{ fontSize: 18, lineHeight: 1 }}>‹‹</span>
        </IconBtn>
        <div style={{ fontSize: 14, color: 'var(--color-subtle)' }}>对话历史</div>
        <IconBtn title="新建对话" onClick={() => {
          if (window.confirm('清空当前对话开新的？')) onNewSession()
        }}>
          <CirclePlus />
        </IconBtn>
      </header>

      <main style={{
        flex: 1, overflowY: 'auto',
        padding: '20px',
        background: 'var(--color-base)',
        position: 'relative',
      }}>
        <BgPineLayer />
        {error && <ErrorBanner>{error}</ErrorBanner>}
        <div style={{ position: 'relative', zIndex: 1 }}>
          {messages.length === 0 ? (
            <p style={{ textAlign: 'center', color: 'var(--color-subtle)', padding: '40px 0' }}>
              还没说过话呢
            </p>
          ) : (
            messages.map((m, i) => (
              <ChatBubble key={i} message={m} taskRec={null} />
            ))
          )}
          <div ref={endRef} />
        </div>
      </main>
    </div>
  )
}


// ════════════ 用户气泡（无泡尾，堆叠用，自带 opacity 过渡） ════════════

function UserBubble({ text, opacity }) {
  const [expanded, setExpanded] = useState(false)
  const tooLong = text.length > BUBBLE_MAX_LEN
  const display = (tooLong && !expanded) ? text.slice(0, BUBBLE_MAX_LEN) + '...' : text

  return (
    <div
      style={{
        background: 'var(--color-primary)',
        color: '#fff',
        borderRadius: 14,
        padding: '8px 14px',
        fontSize: 13,
        lineHeight: 1.45,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        opacity,
        transition: 'opacity 400ms ease-out, transform 400ms ease-out',
        maxWidth: '100%',
      }}
    >
      {display}
      {tooLong && (
        <button
          onClick={() => setExpanded(!expanded)}
          style={{
            marginLeft: 6,
            background: 'transparent', border: 'none',
            color: 'rgba(255,255,255,0.85)',
            fontSize: 12, fontFamily: 'inherit',
            cursor: 'pointer', textDecoration: 'underline',
          }}
        >
          {expanded ? '收起' : '更多'}
        </button>
      )}
    </div>
  )
}


// ════════════ 小白气泡（带泡尾，永远只显示最新一条） ════════════

function SpeechBubble({ who, text }) {
  const [expanded, setExpanded] = useState(false)
  const isAi = who === 'ai'
  const tooLong = text.length > BUBBLE_MAX_LEN
  const display = (tooLong && !expanded) ? text.slice(0, BUBBLE_MAX_LEN) + '...' : text

  return (
    <div style={{
      position: 'relative',
      maxWidth: '78%',
      zIndex: 1,
    }}>
      <div style={{
        background: isAi ? 'var(--color-surface)' : 'var(--color-primary)',
        border: `1.5px solid ${isAi ? 'var(--color-line)' : 'var(--color-primary)'}`,
        color: isAi ? 'var(--color-text)' : '#fff',
        borderRadius: 16,
        padding: '12px 16px',
        fontSize: 14,
        lineHeight: 1.5,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        boxShadow: '0 1px 0 rgba(0,0,0,0.02)',
      }}>
        {display}
        {tooLong && (
          <button
            onClick={() => setExpanded(!expanded)}
            style={{
              marginLeft: 6,
              background: 'transparent', border: 'none',
              color: isAi ? 'var(--color-primary)' : 'rgba(255,255,255,0.85)',
              fontSize: 12, fontFamily: 'inherit',
              cursor: 'pointer', textDecoration: 'underline',
            }}
          >
            {expanded ? '收起' : '更多'}
          </button>
        )}
      </div>

      {/* 泡尾：AI 在底，用户在顶 */}
      <BubbleTail
        isAi={isAi}
        bgColor={isAi ? 'var(--color-surface)' : 'var(--color-primary)'}
        borderColor={isAi ? 'var(--color-line)' : 'var(--color-primary)'}
      />
    </div>
  )
}

function BubbleTail({ isAi, bgColor, borderColor }) {
  // 用旋转的方块做泡尾，AI 在气泡底部下方，用户在顶部上方
  return (
    <div style={{
      position: 'absolute',
      [isAi ? 'bottom' : 'top']: -7,
      left: '50%',
      transform: 'translateX(-50%) rotate(45deg)',
      width: 12, height: 12,
      background: bgColor,
      // 三边边框来模拟尖角
      borderRight: isAi ? `1.5px solid ${borderColor}` : 'none',
      borderBottom: isAi ? `1.5px solid ${borderColor}` : 'none',
      borderTop: isAi ? 'none' : `1.5px solid ${borderColor}`,
      borderLeft: isAi ? 'none' : `1.5px solid ${borderColor}`,
    }} />
  )
}


// ════════════ 任务推荐按钮 ════════════

function TaskActionRow({ keyword, minutes, onRecord, onDismiss }) {
  return (
    <div style={{
      display: 'flex', gap: 10,
      position: 'relative', zIndex: 1,
    }}>
      <button
        onClick={onRecord}
        style={{
          padding: '8px 18px',
          borderRadius: 'var(--radius)',
          border: '1px solid var(--color-primary)',
          background: 'var(--color-primary)',
          color: '#fff',
          fontSize: 13, fontFamily: 'inherit', cursor: 'pointer',
        }}
      >
        记下「{keyword}」{minutes ? ` ${minutes} min` : ''}
      </button>
      <button
        onClick={onDismiss}
        style={{
          padding: '8px 18px',
          borderRadius: 'var(--radius)',
          border: '1px solid var(--color-line)',
          background: 'transparent',
          color: 'var(--color-subtle)',
          fontSize: 13, fontFamily: 'inherit', cursor: 'pointer',
        }}
      >
        再聊聊
      </button>
    </div>
  )
}


// ════════════ 工具 ════════════

function BgPineLayer() {
  return (
    <div style={{
      position: 'absolute', inset: 0, pointerEvents: 'none',
      opacity: 0.06,
      backgroundRepeat: 'repeat',
      backgroundSize: '360px 240px',
      backgroundImage: `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='360' height='240' viewBox='0 0 360 240'><g fill='%234896c4' opacity='0.45'><path d='M40 200 L30 160 L50 160 Z M35 170 L25 130 L45 130 Z M37 140 L28 100 L46 100 Z'/><path d='M140 210 L128 170 L152 170 Z M134 180 L124 140 L144 140 Z'/><path d='M260 200 L248 160 L272 160 Z M254 170 L244 130 L264 130 Z M256 140 L247 100 L265 100 Z M258 110 L250 80 L266 80 Z'/><path d='M340 205 L330 170 L350 170 Z M335 180 L325 145 L345 145 Z'/></g></svg>")`,
    }} />
  )
}

function ErrorBanner({ children }) {
  return (
    <div style={{
      padding: '10px 14px', marginBottom: 12,
      borderRadius: 'var(--radius)',
      background: '#fee', border: '1px solid #fbb',
      fontSize: 13, color: '#933',
      position: 'relative', zIndex: 1,
    }}>{children}</div>
  )
}

function IconBtn({ children, onClick, title }) {
  return (
    <button
      onClick={onClick}
      title={title}
      style={{
        width: 36, height: 36,
        background: 'transparent', border: 'none',
        borderRadius: 8, cursor: 'pointer',
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

function HistoryIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none">
      <rect x="4" y="4" width="16" height="16" rx="2" stroke="currentColor" strokeWidth="1.4"/>
      <line x1="8" y1="9"  x2="16" y2="9"  stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
      <line x1="8" y1="13" x2="16" y2="13" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
      <line x1="8" y1="17" x2="13" y2="17" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
    </svg>
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
        stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"
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
