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

// 自动重试配置：只对 GET 做（幂等），其他方法失败就失败
const _GET_MAX_RETRIES = 3   // 首次 + 2 次重试
const _GET_RETRY_DELAY = 500 // ms


async function _doFetch(path, opts = {}) {
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


/**
 * apiFetch：带 JWT 的后端调用。
 *
 * 自动重试策略：
 *   - 只对 GET 请求重试（幂等，安全）
 *   - POST/PUT/PATCH/DELETE 失败一次就抛，避免重复创建/重复扣除等副作用
 *   - 重试条件：TypeError（浏览器 fetch 层失败，如 Failed to fetch）或 5xx 响应
 *   - 不重试：4xx 业务错、401 未授权
 */
export async function apiFetch(path, opts = {}) {
  const method = (opts.method || 'GET').toUpperCase()
  const retryable = method === 'GET'
  const maxAttempts = retryable ? _GET_MAX_RETRIES : 1

  let lastErr = null
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return await _doFetch(path, opts)
    } catch (e) {
      lastErr = e
      // 判断是否值得重试：网络层抛 TypeError；业务层抛 ApiError 只在 5xx 时重试
      const isNetworkError = e instanceof TypeError
      const is5xx = e instanceof ApiError && e.status >= 500 && e.status < 600
      const shouldRetry = retryable && (isNetworkError || is5xx)

      if (!shouldRetry || attempt === maxAttempts - 1) throw e

      console.warn(`[apiFetch] GET ${path} 第 ${attempt + 1} 次失败（${e.message}），${_GET_RETRY_DELAY}ms 后重试`)
      await new Promise(r => setTimeout(r, _GET_RETRY_DELAY))
    }
  }
  throw lastErr
}
