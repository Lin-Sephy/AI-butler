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
 *                  DS 判定用户定稿时返回 confirmed=true
 *
 * @param {{message: string, sessionId: string, mode?: 'chat'|'plan', energyLevel?: number|null}} opts
 * @returns {Promise<{
 *   reply: string,
 *   signal: object,          // v5 始终为空 {}，保留字段为了不破向后兼容
 *   task_recommendation: null,  // v5 始终 null
 *   show_action_buttons: false,  // v5 始终 false
 *   energy_confirm_needed: false,  // v5 精力系统已砍
 *   confirmed: boolean,      // v5 新增：计划模式下 DS 是否判定用户定稿
 * }>}
 */
export async function sendMessage({ message, sessionId, mode = 'chat', energyLevel = null }) {
  return apiFetch('/api/chat', {
    method: 'POST',
    body: {
      message,
      session_id: sessionId,
      mode,
      energy_level: energyLevel,
    },
  })
}

/**
 * 计划确认后从对话里提取结构化 tasks（v5.0 新增）。
 *
 * DS 返回 confirmed=true 后，前端调这个端点。拿到候选 tasks 列表，
 * 让用户编辑（删/改时长/改项目），然后走 /api/task/record 批量写入。
 *
 * @param {string} sessionId
 * @returns {Promise<{tasks: Array<{
 *   keyword: string,
 *   minutes: number|null,
 *   task_type: 'work'|'rest',
 *   scheduled_at: string|null,   // "YYYY-MM-DD HH:MM"
 *   project_name: string|null,
 *   project_id: number|null,
 * }>}>}
 */
export async function planExtract(sessionId) {
  return apiFetch('/api/plan/extract', {
    method: 'POST',
    body: { session_id: sessionId },
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
