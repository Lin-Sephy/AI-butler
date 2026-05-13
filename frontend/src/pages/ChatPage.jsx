/**
 * 聊天页 v2 漫画气泡布局：
 *
 *   - 白鼬永远居中超大，可点逗（状态动效永远活着）
 *   - 顶气泡：小白最新一句，泡尾下指白鼬
 *   - 底气泡：你最新一句，泡尾上指白鼬
 *   - 任务推荐按钮：紧贴 AI 气泡下方独立一行
 *   - 想看完整对话：右上角 📃 切到历史滚动列表视图
 *
 * 数据：useChat() 提供 messages/send/resetSession/mode/planConfirmed
 *
 * v5.0 改动：砍了 v4 的推任务气泡（pendingTaskRec/record/dismissRec 链路已不存在）。
 * 模式切换 UI（chat ↔ plan）和计划确认界面（planConfirmed 触发）由前端小克后续补。
 */

import { useState, useEffect } from 'react'
import { useChat } from '../contexts/ChatContext.jsx'
import { useConfirm } from '../contexts/ConfirmContext.jsx'
import StoatHalf from '../components/StoatHalf.jsx'
import SettingsPanel from '../components/SettingsPanel.jsx'
import PlanConfirmModal from '../components/PlanConfirmModal.jsx'
import DeleteConfirmModal from '../components/DeleteConfirmModal.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import { listSessions } from '../lib/chatApi.js'
import { cleanAssistantText, renderAssistantText } from '../lib/text.jsx'

const STOAT_WIDTH = 220
const BUBBLE_MAX_LEN = 100      // 小白气泡：超过截断 + "更多"
const USER_BUBBLE_MAX_LEN = 50  // 用户气泡：更短（防堆高度挡白鼬）

// 闲聊模式下打出这些词时顺手提示切任务模式
const PLAN_INTENT_KEYWORDS = [
  '安排', '计划', '改一下', '删', '取消', '推到', '推后',
  '加一个', '加个', '今天做', '明天做', '任务', '待办',
]
function hasPlanIntent(text) {
  if (!text) return false
  return PLAN_INTENT_KEYWORDS.some(k => text.includes(k))
}

export default function ChatPage() {
  const {
    messages, loading, error, send, resetSession, mode, setMode,
    sessionId, planConfirmed, lastCreatedTasks, clearPlanConfirmed,
    pendingDeletes, clearPendingDeletes, switchSession,
  } = useChat()
  const confirm = useConfirm()

  const [view, setView] = useState('main')   // 'main' | 'history'
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [modeHint, setModeHint] = useState(null)  // 切换提示条文案，1.8s 自动消失
  const [thinkingPhase, setThinkingPhase] = useState(0)  // 等 DS 回复时：0 默认/1 >3s/2 >8s

  // sending 满 3s / 8s 换 thinking 文案，缓解等待焦虑
  useEffect(() => {
    if (!sending) { setThinkingPhase(0); return }
    const t1 = setTimeout(() => setThinkingPhase(1), 3000)
    const t2 = setTimeout(() => setThinkingPhase(2), 8000)
    return () => { clearTimeout(t1); clearTimeout(t2) }
  }, [sending])

  function handleModeChange(next) {
    if (next === mode) return
    setMode(next)
    setModeHint(next === 'plan' ? '小白切换到任务模式了' : '回到闲聊模式')
    setTimeout(() => setModeHint(null), 1800)
  }

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
        currentSessionId={sessionId}
        onBack={() => setView('main')}
        onNewSession={async () => {
          await resetSession()
          setView('main')
        }}
        onSelectSession={async id => {
          await switchSession(id)
          setView('main')
        }}
        error={error}
      />
    )
  }

  // 小白：最新一条（保留泡尾居中）；你：最近 4 条堆叠右对齐淡化
  const latestAi   = [...messages].reverse().find(m => m.role === 'assistant')
  // 保留每条用户消息在 messages 里的绝对索引做 key（避免消息变动时 React remount 动画）
  const userMsgs = messages
    .map((m, absIdx) => ({ ...m, absIdx }))
    .filter(m => m.role === 'user')
  const recentUsers = userMsgs.slice(-4)
  const USER_OPACITY = [0.15, 0.35, 0.65, 1]   // 最老 → 最新

  // 白鼬状态：sending 时 thinking；用户在输入框打字时 listening；否则 idle
  const stoatState = sending ? 'thinking' : (input.length > 0 ? 'listening' : 'idle')

  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      minHeight: 'calc(100% + 80px)',
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
        <ModeToggle mode={mode} onChange={handleModeChange} />
        <IconBtn title="历史对话" onClick={() => setView('history')}>
          <HistoryIcon />
        </IconBtn>
        <IconBtn title="新建对话" onClick={async () => {
          if (await confirm('清空当前对话开新的？')) resetSession()
        }}>
          <CirclePlus />
        </IconBtn>
        <IconBtn title="设置" onClick={() => setSettingsOpen(true)}>
          <Gear />
        </IconBtn>
      </header>

      {settingsOpen && (
        <SettingsPanel onClose={() => setSettingsOpen(false)} />
      )}

      {planConfirmed && lastCreatedTasks.length > 0 && (
        <PlanConfirmModal
          initialTasks={lastCreatedTasks}
          sessionId={sessionId}
          onClose={clearPlanConfirmed}
        />
      )}

      {pendingDeletes.length > 0 && (
        <DeleteConfirmModal
          pendingTasks={pendingDeletes}
          onClose={clearPendingDeletes}
        />
      )}

      {/* ─── 主舞台 ─── */}
      <main style={{
        flex: 1,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        padding: '20px 20px 100px',
        position: 'relative',
        background: 'var(--color-base)',
        gap: 12,
      }}>
        {/* 针叶背景 */}
        <BgPineLayer />

        {error && (
          <ErrorBanner>{error}</ErrorBanner>
        )}

        {modeHint && <ModeHintBanner>{modeHint}</ModeHintBanner>}

        {/* 顶气泡：小白说 —— 思考时藏掉，让头顶 3 点泡泡当唯一焦点 */}
        {!sending && latestAi && (
          <SpeechBubble who="ai" text={latestAi.content} />
        )}

        {/* 白鼬居中 */}
        <div style={{ position: 'relative', zIndex: 1 }}>
          <StoatHalf view="full" state={stoatState} width={STOAT_WIDTH} />
        </div>

        {/* thinking 动态文案：等 DS 超过 3s 才显，缓解"是不是卡住了"焦虑 */}
        {sending && thinkingPhase > 0 && (
          <div style={{
            fontSize: 12,
            color: 'var(--color-subtle)',
            zIndex: 1,
            marginTop: -4,
            opacity: 0.8,
          }}>
            {thinkingPhase === 1
              ? (mode === 'plan' ? '在翻你任务栏...' : '在想怎么说...')
              : '让小白慢慢想...'}
          </div>
        )}

        {/* 闲聊模式下用户打出"安排/计划/删/取消..."等词时顺手提示切任务 */}
        {mode === 'chat' && hasPlanIntent(input) && !sending && (
          <button
            type="button"
            onClick={() => handleModeChange('plan')}
            style={{
              marginTop: -4,
              padding: '5px 12px',
              borderRadius: 999,
              border: '1px solid var(--color-primary)',
              background: 'var(--color-primary-soft)',
              color: 'var(--color-primary)',
              fontSize: 12, fontFamily: 'inherit',
              cursor: 'pointer',
              zIndex: 1,
              transition: 'var(--transition) ease-out',
            }}
          >
            切到任务模式 →
          </button>
        )}

        {/* 你说：堆叠右对齐贴底，新在底老在顶，opacity 渐弱 */}
        {recentUsers.length > 0 && (
          <div style={{
            position: 'absolute',
            right: 20, bottom: 16,
            display: 'flex', flexDirection: 'column', gap: 6,
            alignItems: 'flex-end',
            zIndex: 2,
            maxWidth: '85%',
          }}>
            {recentUsers.map((m, i) => {
              const ageIndex = recentUsers.length - 1 - i   // 0 = 最新
              const opacity = USER_OPACITY[USER_OPACITY.length - 1 - ageIndex] ?? 0.1
              return (
                <UserBubble key={`u-${m.absIdx}`} text={m.content} opacity={opacity} />
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
            opacity: sending ? 0.55 : 1,
            cursor: sending ? 'not-allowed' : 'text',
            transition: 'opacity var(--transition)',
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

function HistoryView({ currentSessionId, onBack, onNewSession, onSelectSession, error }) {
  const confirm = useConfirm()
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [localError, setLocalError] = useState(null)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        setLoading(true)
        setLocalError(null)
        const data = await listSessions()
        if (alive) setSessions(data.sessions || [])
      } catch (e) {
        if (alive) setLocalError(e.message)
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => { alive = false }
  }, [])

  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      minHeight: 'calc(100% + 80px)',
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
        <IconBtn title="新建对话" onClick={async () => {
          if (await confirm('清空当前对话开新的？')) onNewSession()
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
        {localError && <ErrorBanner>{localError}</ErrorBanner>}
        <div style={{ position: 'relative', zIndex: 1 }}>
          {loading ? (
            <p style={{ textAlign: 'center', color: 'var(--color-subtle)', padding: '40px 0' }}>
              正在翻对话……
            </p>
          ) : sessions.length === 0 ? (
            <p style={{ textAlign: 'center', color: 'var(--color-subtle)', padding: '40px 0' }}>
              还没有历史对话
            </p>
          ) : (
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
            }}>
              {sessions.map(s => {
                const isCurrent = s.session_id === currentSessionId
                return (
                  <button
                    key={s.session_id}
                    type="button"
                    onClick={() => onSelectSession(s.session_id)}
                    style={{
                      width: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 12,
                      padding: '14px 16px',
                      borderRadius: 8,
                      border: `1px solid ${isCurrent ? 'var(--color-primary)' : 'var(--color-line)'}`,
                      background: isCurrent ? 'var(--color-primary-soft)' : 'var(--color-surface)',
                      color: 'var(--color-text)',
                      font: 'inherit',
                      textAlign: 'left',
                      cursor: 'pointer',
                      boxShadow: '0 1px 0 rgba(0,0,0,0.02)',
                    }}
                  >
                    <span style={{
                      fontSize: 14,
                      lineHeight: 1.4,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>
                      {s.title}
                    </span>
                    {isCurrent && (
                      <span style={{
                        flexShrink: 0,
                        fontSize: 11,
                        color: 'var(--color-primary)',
                      }}>
                        当前
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}


// ════════════ 模式分隔符（历史视图里相邻两条消息 mode 变化时插入） ════════════

function ModeDivider({ mode }) {
  const label = mode === 'plan' ? '任务模式' : '闲聊模式'
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        margin: '20px 4px 16px',
        color: 'var(--color-muted)',
        fontSize: 11,
        letterSpacing: '0.12em',
        userSelect: 'none',
      }}
      aria-label={`以下是${label}的对话`}
    >
      <div style={{ flex: 1, height: 1, background: 'var(--color-line-soft)' }} />
      <span>— {label} —</span>
      <div style={{ flex: 1, height: 1, background: 'var(--color-line-soft)' }} />
    </div>
  )
}


// ════════════ 用户气泡（无泡尾，堆叠用，自带 opacity 过渡） ════════════

function UserBubble({ text, opacity }) {
  const [expanded, setExpanded] = useState(false)
  const tooLong = text.length > USER_BUBBLE_MAX_LEN
  const display = (tooLong && !expanded) ? text.slice(0, USER_BUBBLE_MAX_LEN) + '...' : text

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
  const cleanText = isAi ? cleanAssistantText(text) : text
  const tooLong = cleanText.length > BUBBLE_MAX_LEN
  const display = (tooLong && !expanded) ? cleanText.slice(0, BUBBLE_MAX_LEN) + '...' : cleanText
  const displayNode = isAi ? renderAssistantText(display) : display

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
        {displayNode}
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

function ModeToggle({ mode, onChange }) {
  const isPlan = mode === 'plan'
  return (
    <div
      onClick={() => onChange(isPlan ? 'chat' : 'plan')}
      title={isPlan ? '任务模式（点击切回闲聊）' : '闲聊模式（点击切到任务）'}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 5,
        marginRight: 8,
        cursor: 'pointer',
        fontSize: 11,
        fontFamily: "'Inter', system-ui, sans-serif",
        userSelect: 'none',
      }}
    >
      <span style={{
        color: isPlan ? 'var(--color-subtle)' : 'var(--color-primary)',
        opacity: isPlan ? 0.5 : 1,
        transition: 'var(--transition) ease-out',
      }}>
        闲聊
      </span>
      <div
        style={{
          width: 34, height: 18,
          borderRadius: 999,
          border: `1px solid ${isPlan ? 'var(--color-primary)' : 'var(--color-line)'}`,
          background: isPlan ? 'var(--color-primary)' : 'var(--color-accent-soft)',
          position: 'relative',
          transition: 'background var(--transition) ease-out, border-color var(--transition) ease-out',
          flexShrink: 0,
        }}
      >
        <span style={{
          position: 'absolute',
          top: 1, left: isPlan ? 17 : 1,
          width: 14, height: 14,
          borderRadius: '50%',
          background: '#fff',
          transition: 'left var(--transition) ease-out',
          boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
        }} />
      </div>
      <span style={{
        color: isPlan ? 'var(--color-primary)' : 'var(--color-subtle)',
        opacity: isPlan ? 1 : 0.5,
        transition: 'var(--transition) ease-out',
      }}>
        任务
      </span>
    </div>
  )
}

function ModeHintBanner({ children }) {
  return (
    <div style={{
      position: 'absolute',
      top: 12, left: '50%',
      transform: 'translateX(-50%)',
      padding: '6px 14px',
      borderRadius: 999,
      background: 'var(--color-primary)',
      color: '#fff',
      fontSize: 12,
      boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
      zIndex: 3,
      animation: 'modeHintFade 1.8s ease-out',
    }}>
      {children}
    </div>
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
  // viewBox 对齐 HistoryIcon / Gear 的 0 0 24 24
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="1.4" />
      <line x1="12" y1="8" x2="12" y2="16" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <line x1="8" y1="12" x2="16" y2="12" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
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
      fontSize: 14,
    }}>
      {children}
    </div>
  )
}
