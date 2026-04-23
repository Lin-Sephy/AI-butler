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


/**
 * 把技术错误转成用户可读文案。
 * message 只给 UI 展示用；技术细节（endpoint/status/body）走 console.error。
 */
function _userFriendlyMessage(status, detail) {
  if (status === 0) return '网络有点慢，等等再试'
  if (status === 401) return '登录失效了，刷新一下页面'
  if (status >= 500) return '小白那边出了点问题，稍等'
  if (status >= 400) {
    // 4xx 通常是后端返的业务 detail（中文可读），长度合理就直接用
    if (typeof detail === 'string' && detail && detail.length < 200) return detail
    return '请求有问题，请检查后重试'
  }
  return '出了点问题，稍等再试'
}


async function _doFetch(path, opts = {}) {
  const { method = 'GET', body, headers = {} } = opts

  // 取当前 session 的 access_token
  const { data: { session } } = await supabase.auth.getSession()
  if (!session?.access_token) {
    console.error(`[api] ${method} ${path} 中止：无 session`)
    throw new ApiError(401, _userFriendlyMessage(401), null)
  }

  const finalHeaders = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${session.access_token}`,
    ...headers,
  }

  const url = path.startsWith('http') ? path : `${API_BASE}${path}`

  let resp
  try {
    resp = await fetch(url, {
      method,
      headers: finalHeaders,
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch (e) {
    // 浏览器 fetch 层失败：Failed to fetch / DNS / TLS / 网络断开
    // 技术细节进 console，UI 层看到的 message 归一化（status=0 作为"网络层"标识）
    console.error(`[api] ${method} ${path} 网络层失败:`, e.message)
    throw new ApiError(0, _userFriendlyMessage(0), null)
  }

  let data = null
  const ctype = resp.headers.get('content-type') || ''
  if (ctype.includes('application/json')) {
    data = await resp.json().catch(() => null)
  } else {
    data = await resp.text().catch(() => null)
  }

  if (!resp.ok) {
    const detail = data?.detail || data || resp.statusText
    // Console 保留完整技术细节，方便 F12 定位
    console.error(`[api] ${method} ${path} → ${resp.status}`, {
      endpoint: path,
      method,
      status: resp.status,
      body: data,
    })
    // UI 层看到的 message 归一化
    throw new ApiError(resp.status, _userFriendlyMessage(resp.status, detail), data)
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
      // 网络层（status=0，原 TypeError）和 5xx 值得重试；4xx/401 是业务错，不重试
      const shouldRetry = retryable
        && e instanceof ApiError
        && (e.status === 0 || (e.status >= 500 && e.status < 600))

      if (!shouldRetry || attempt === maxAttempts - 1) throw e

      console.warn(`[api] GET ${path} 第 ${attempt + 1} 次失败（status=${e.status}），${_GET_RETRY_DELAY}ms 后重试`)
      await new Promise(r => setTimeout(r, _GET_RETRY_DELAY))
    }
  }
  throw lastErr
}
