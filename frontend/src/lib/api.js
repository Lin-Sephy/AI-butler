/**
 * 后端 API 调用封装。
 *
 * 自动从当前 Supabase session 取 access_token 加进 Authorization header。
 * 用法：
 *   const tasks = await apiFetch('/api/tasks/today')
 *   await apiFetch('/api/task/record', { method: 'POST', body: { task_keyword: '...' } })
 */

import { supabase } from './supabase'

const API_BASE = import.meta.env.VITE_API_BASE_URL

if (!API_BASE) {
  throw new Error('缺少 VITE_API_BASE_URL。检查 frontend/.env.local。')
}

export class ApiError extends Error {
  constructor(status, message, body) {
    super(message)
    this.status = status
    this.body = body
  }
}

export async function apiFetch(path, opts = {}) {
  const { method = 'GET', body, headers = {} } = opts

  // 取当前 session 的 access_token
  const { data: { session } } = await supabase.auth.getSession()
  if (!session?.access_token) {
    throw new ApiError(401, '未登录或 session 已失效', null)
  }

  const finalHeaders = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${session.access_token}`,
    ...headers,
  }

  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  const resp = await fetch(url, {
    method,
    headers: finalHeaders,
    body: body ? JSON.stringify(body) : undefined,
  })

  let data = null
  const ctype = resp.headers.get('content-type') || ''
  if (ctype.includes('application/json')) {
    data = await resp.json().catch(() => null)
  } else {
    data = await resp.text().catch(() => null)
  }

  if (!resp.ok) {
    const detail = data?.detail || data || resp.statusText
    throw new ApiError(resp.status, `API ${method} ${path} 失败: ${detail}`, data)
  }

  return data
}
