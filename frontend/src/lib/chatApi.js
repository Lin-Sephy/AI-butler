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
 * 发送一条聊天消息。
 *
 * v5.0：
 *   - mode='chat'：闲聊模式，DS 纯文本输出，confirmed 永远 false
 *   - mode='plan'：计划模式，DS 注册 function calling 工具按需查数据；
 *                  DS 判定用户定稿时返回 confirmed=true；本轮 DS 写入的任务在 created_tasks 里
 *
 * @param {{message: string, sessionId: string, mode?: 'chat'|'plan'}} opts
 * @returns {Promise<{
 *   reply: string,
 *   confirmed: boolean,         // 计划模式下 DS 是否判定用户定稿
 *   created_tasks: Array<{task_id, keyword, minutes, scheduled_at, status}>,  // 本轮 DS 写入的任务
 * }>}
 */
export async function sendMessage({ message, sessionId, mode = 'chat' }) {
  return apiFetch('/api/chat', {
    method: 'POST',
    body: {
      message,
      session_id: sessionId,
      mode,
    },
  })
}
