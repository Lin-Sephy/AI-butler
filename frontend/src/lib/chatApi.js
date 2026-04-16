/**
 * 聊天相关 API 封装。
 *
 * 纯 async 函数，不碰 React state——state 编排在 ChatContext 里。
 * 所有函数自动通过 apiFetch 带 JWT（见 api.js）。
 */

import { apiFetch } from './api.js'

/**
 * 创建新会话。
 * @returns {Promise<{session_id: string, greeting: string}>}
 */
export async function newSession() {
  return apiFetch('/api/session/new', { method: 'POST' })
}

/**
 * 加载指定会话的历史消息。
 * @param {string} sessionId
 * @returns {Promise<{messages: Array<{role: 'user'|'assistant', content: string}>}>}
 */
export async function loadHistory(sessionId) {
  return apiFetch(`/api/session/${sessionId}/messages`)
}

/**
 * 发送一条聊天消息，返回 AI 回复 + 信号 + 是否推任务。
 * @param {{message: string, sessionId: string, persona?: string, energyLevel?: number|null}} opts
 * @returns {Promise<{
 *   reply: string,
 *   signal: object,
 *   task_recommendation: object|null,
 *   show_action_buttons: boolean,
 *   energy_confirm_needed: boolean,
 * }>}
 */
export async function sendMessage({ message, sessionId, persona = 'infp', energyLevel = null }) {
  return apiFetch('/api/chat', {
    method: 'POST',
    body: {
      message,
      session_id: sessionId,
      persona,
      energy_level: energyLevel,
    },
  })
}

/**
 * 把推荐的任务记录到任务栏（idle 状态，不自动开始）。
 * @param {{keyword: string, suggestedMinutes?: number|null, taskType?: 'work'|'rest', detail?: string, energyLevel?: number|null}} opts
 * @returns {Promise<{message: string, task: object}>}
 */
export async function recordTask({
  keyword,
  suggestedMinutes = null,
  taskType = 'work',
  detail = '',
  energyLevel = null,
}) {
  return apiFetch('/api/task/record', {
    method: 'POST',
    body: {
      task_keyword: keyword,
      suggested_minutes: suggestedMinutes,
      task_type: taskType,
      detail,
      energy_level: energyLevel,
    },
  })
}
