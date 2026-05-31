/**
 * 聊天会话上下文。
 *
 * 挂在 App 外层（main.jsx），跨 tab 切换保持消息历史不丢；
 * sessionId 落 localStorage，跨刷新也保留。
 *
 * 消费方式：
 *   const { messages, mode, send, setMode, planConfirmed, ... } = useChat()
 *
 * 暴露字段：
 *   - sessionId: string | null
 *   - messages: Array<{role: 'user'|'assistant', content: string}>
 *   - loading: boolean（首次 bootstrap 是否还在进行）
 *   - error: string | null
 *   - mode: 'chat' | 'plan'（v5.0 新增：当前会话模式）
 *   - planConfirmed: boolean（v5.0 新增：计划模式下 DS 判定最近一轮定稿，
 *                             前端可据此触发 planExtract + 弹确认界面）
 *
 * 暴露方法：
 *   - send(text)                发消息，用当前 mode
 *   - setMode(mode)             切换闲聊/计划模式（ui 层调）
 *   - clearPlanConfirmed()      用户消费完 confirmed 信号后清掉（防重复触发）
 *   - resetSession()            清空当前会话，新建一个（顶部 ⊕ 新建对话）
 */

import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import { useAuth } from './AuthContext.jsx'
import { newSession, loadHistory, sendMessage } from '../lib/chatApi.js'
import { initLocalDb, loadSessionMessages, saveSessionMessages, addSessionMessage } from '../lib/localDb.js'

const SESSION_KEY = 'ai-butler-session-id'
const MODE_KEY = 'ai-butler-chat-mode'
const COMPANION_NAME_KEY = 'ai-butler-companion-name'
const DEFAULT_GREETING = '来啦～'
const DEFAULT_COMPANION_NAME = '小白'

const ChatContext = createContext(null)

// localStorage 读 mode，不是合法值就回退 'chat'
function _readSavedMode() {
  try {
    const raw = localStorage.getItem(MODE_KEY)
    return raw === 'plan' ? 'plan' : 'chat'
  } catch {
    return 'chat'
  }
}

function _readSavedCompanionName() {
  try {
    return localStorage.getItem(COMPANION_NAME_KEY) || DEFAULT_COMPANION_NAME
  } catch {
    return DEFAULT_COMPANION_NAME
  }
}

export function ChatProvider({ children }) {
  const { user, loading: authLoading } = useAuth()

  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [mode, setModeRaw] = useState(_readSavedMode)
  const [companionName, setCompanionNameRaw] = useState(_readSavedCompanionName)
  const [planConfirmed, setPlanConfirmed] = useState(false)
  const [lastCreatedTasks, setLastCreatedTasks] = useState([])   // v5.0 p2: DS 本轮 create_tasks 写入的任务，PlanConfirmModal 事后编辑用
  const [pendingDeletes, setPendingDeletes] = useState([])       // v5: DS 本轮 delete_task(s) 待确认删除的任务

  // setMode 包一层：同步落 localStorage，避免刷新丢
  const setMode = useCallback(next => {
    setModeRaw(next)
    try { localStorage.setItem(MODE_KEY, next) } catch {}
  }, [])

  const setCompanionName = useCallback(next => {
    const clean = (next || '').trim() || DEFAULT_COMPANION_NAME
    setCompanionNameRaw(clean)
    try { localStorage.setItem(COMPANION_NAME_KEY, clean) } catch {}
  }, [])

  const bootstrapped = useRef(false)

  // ── 首次挂载：用户登录好之后引导会话 ──
  useEffect(() => {
    if (authLoading || !user || bootstrapped.current) return
    bootstrapped.current = true

    ;(async () => {
      try {
        await initLocalDb()
        const saved = localStorage.getItem(SESSION_KEY)
        if (saved) {
          const cached = await loadSessionMessages(saved)
          if (cached.length > 0) {
            setMessages(cached.map(msg => ({
              role: msg.role,
              content: msg.content,
              mode: msg.mode,
            })))
          }

          const data = await loadHistory(saved)
          const history = data.messages || []
          const finalHistory = history.length > 0 ? history : (
            cached.length > 0 ? cached.map(msg => ({ role: msg.role, content: msg.content, mode: msg.mode })) : [{ role: 'assistant', content: DEFAULT_GREETING, mode: 'chat' }]
          )
          setSessionId(saved)
          setMessages(finalHistory)
          if (history.length > 0) {
            await saveSessionMessages(saved, history)
          }
        } else {
          const { session_id, greeting } = await newSession()
          localStorage.setItem(SESSION_KEY, session_id)
          setSessionId(session_id)
          setMessages(greeting ? [{ role: 'assistant', content: greeting, mode: 'chat' }] : [])
        }
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    })()
  }, [authLoading, user])

  // ── send：发消息 ──
  const send = useCallback(
    async text => {
      if (!sessionId || !text.trim()) return
      setError(null)
      const userMessage = { role: 'user', content: text, mode }
      setMessages(m => [...m, userMessage])
      addSessionMessage(sessionId, userMessage).catch(() => {})
      try {
        const resp = await sendMessage({ message: text, sessionId, mode })
        const assistantMessage = { role: 'assistant', content: resp.reply, mode }
        setMessages(m => [...m, assistantMessage])
        addSessionMessage(sessionId, assistantMessage).catch(() => {})
        const created = resp.created_tasks || []
        if (created.length > 0) {
          setLastCreatedTasks(created)
          setPlanConfirmed(true)
        }
        const deletes = resp.pending_deletes || []
        if (deletes.length > 0) {
          setPendingDeletes(deletes)
        }
      } catch (e) {
        setError(e.message)
      }
    },
    [sessionId, mode],
  )

  // ── clearPlanConfirmed：confirmed 信号被消费后清掉，防重复触发 ──
  const clearPlanConfirmed = useCallback(() => {
    setPlanConfirmed(false)
    setLastCreatedTasks([])
  }, [])

  const clearPendingDeletes = useCallback(() => {
    setPendingDeletes([])
  }, [])

  // ── resetSession：顶部 ⊕ 新建对话 ──
  const resetSession = useCallback(async () => {
    setError(null)
    try {
      const { session_id, greeting } = await newSession()
      localStorage.setItem(SESSION_KEY, session_id)
      setSessionId(session_id)
      setMessages([{ role: 'assistant', content: greeting || DEFAULT_GREETING, mode: 'chat' }])
      setPlanConfirmed(false)
    } catch (e) {
      setError(e.message)
    }
  }, [])

  const switchSession = useCallback(async nextSessionId => {
    if (!nextSessionId || nextSessionId === sessionId) return
    setError(null)
    try {
      const data = await loadHistory(nextSessionId)
      const history = data.messages || []
      localStorage.setItem(SESSION_KEY, nextSessionId)
      setSessionId(nextSessionId)
      setMessages(history.length > 0 ? history : [{ role: 'assistant', content: DEFAULT_GREETING, mode: 'chat' }])
      setPlanConfirmed(false)
      setLastCreatedTasks([])
      setPendingDeletes([])
    } catch (e) {
      setError(e.message)
      throw e
    }
  }, [sessionId])

  const value = {
    sessionId,
    messages,
    loading,
    error,
    mode,
    companionName,
    planConfirmed,
    lastCreatedTasks,
    pendingDeletes,
    send,
    setMode,
    setCompanionName,
    clearPlanConfirmed,
    clearPendingDeletes,
    resetSession,
    switchSession,
  }

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}

export function useChat() {
  const ctx = useContext(ChatContext)
  if (!ctx) throw new Error('useChat must be used inside <ChatProvider>')
  return ctx
}
