/**
 * 聊天会话上下文。
 *
 * 挂在 App 外层（main.jsx），跨 tab 切换保持消息历史不丢；
 * sessionId 落 localStorage，跨刷新也保留。
 *
 * 消费方式：
 *   const { messages, pendingTaskRec, send, record, ... } = useChat()
 *
 * 暴露字段：
 *   - sessionId: string | null
 *   - messages: Array<{role: 'user'|'assistant', content: string}>
 *   - loading: boolean（首次 bootstrap 是否还在进行）
 *   - error: string | null
 *   - pendingTaskRec: 上一条 AI 回复里的任务推荐对象，或 null
 *       形如 { task_keyword, suggested_minutes, task_type, reply }
 *   - energyConfirmNeeded: boolean（上一条 AI 感知精力偏差需要确认）
 *
 * 暴露方法：
 *   - send(text, opts?)                 发消息，append user + assistant
 *   - record()                          把当前 pendingTaskRec 落到任务栏，返回 { task }
 *   - dismissRec()                      "再聊聊"：清掉推荐按钮不记录
 *   - resetSession()                    清空当前会话，新建一个（顶部 ⊕ 新建对话）
 */

import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import { useAuth } from './AuthContext.jsx'
import { newSession, loadHistory, sendMessage, recordTask } from '../lib/chatApi.js'

const SESSION_KEY = 'ai-butler-session-id'

const ChatContext = createContext(null)

export function ChatProvider({ children }) {
  const { user, loading: authLoading } = useAuth()

  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [pendingTaskRec, setPendingTaskRec] = useState(null)
  const [energyConfirmNeeded, setEnergyConfirmNeeded] = useState(false)

  const bootstrapped = useRef(false)

  // ── 首次挂载：用户登录好之后引导会话 ──
  useEffect(() => {
    if (authLoading || !user || bootstrapped.current) return
    bootstrapped.current = true

    ;(async () => {
      try {
        const saved = localStorage.getItem(SESSION_KEY)
        if (saved) {
          // 有历史 session → 拉历史
          const data = await loadHistory(saved)
          setSessionId(saved)
          setMessages(data.messages || [])
        } else {
          // 无 session → 新建
          const { session_id, greeting } = await newSession()
          localStorage.setItem(SESSION_KEY, session_id)
          setSessionId(session_id)
          setMessages(greeting ? [{ role: 'assistant', content: greeting }] : [])
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
    async (text, { persona = 'infp' } = {}) => {
      if (!sessionId || !text.trim()) return
      setError(null)
      // 本地乐观 append 用户消息
      setMessages(m => [...m, { role: 'user', content: text }])
      try {
        const resp = await sendMessage({ message: text, sessionId, persona })
        setMessages(m => [...m, { role: 'assistant', content: resp.reply }])
        setPendingTaskRec(
          resp.show_action_buttons && resp.task_recommendation ? resp.task_recommendation : null,
        )
        setEnergyConfirmNeeded(!!resp.energy_confirm_needed)
      } catch (e) {
        setError(e.message)
      }
    },
    [sessionId],
  )

  // ── record：把推荐落到任务栏 ──
  const record = useCallback(async () => {
    if (!pendingTaskRec) return null
    const keyword = pendingTaskRec.task_keyword
    try {
      const resp = await recordTask({
        keyword,
        suggestedMinutes: pendingTaskRec.suggested_minutes,
        taskType: pendingTaskRec.task_type || 'work',
      })
      setPendingTaskRec(null)
      // 用一条 AI 侧系统提示消息 "记住了"
      setMessages(m => [
        ...m,
        { role: 'assistant', content: `已记录「${keyword}」～`, _meta: 'task_recorded' },
      ])
      return resp
    } catch (e) {
      setError(e.message)
      return null
    }
  }, [pendingTaskRec])

  // ── dismissRec："再聊聊" ──
  const dismissRec = useCallback(() => {
    setPendingTaskRec(null)
  }, [])

  // ── resetSession：顶部 ⊕ 新建对话 ──
  const resetSession = useCallback(async () => {
    setError(null)
    try {
      const { session_id, greeting } = await newSession()
      localStorage.setItem(SESSION_KEY, session_id)
      setSessionId(session_id)
      setMessages(greeting ? [{ role: 'assistant', content: greeting }] : [])
      setPendingTaskRec(null)
      setEnergyConfirmNeeded(false)
    } catch (e) {
      setError(e.message)
    }
  }, [])

  const value = {
    sessionId,
    messages,
    loading,
    error,
    pendingTaskRec,
    energyConfirmNeeded,
    send,
    record,
    dismissRec,
    resetSession,
  }

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}

export function useChat() {
  const ctx = useContext(ChatContext)
  if (!ctx) throw new Error('useChat must be used inside <ChatProvider>')
  return ctx
}
