const CUSTOM_PERSONA_MAX_LENGTH = 1000
const JWKS_CACHE_TTL_MS = 60 * 60 * 1000

let jwksCache = null
let jwksCacheUntil = 0

export default {
  async fetch(request, env) {
    return handleRequest(request, env)
  },
}

async function handleRequest(request, env) {
  const corsHeaders = getCorsHeaders(request, env)

  if (request.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: corsHeaders })
  }

  const url = new URL(request.url)

  try {
    if (url.pathname === '/api/health' && request.method === 'GET') {
      return json({
        status: 'ok',
        runtime: 'cloudflare-workers',
        service: 'ai-butler-workers-api',
      }, 200, corsHeaders)
    }

    if (url.pathname === '/api/edge-check/auth' && request.method === 'GET') {
      const payload = await requireUser(request, env)
      return json({
        ok: true,
        user_id: payload.sub,
        aud: payload.aud,
        role: payload.role,
      }, 200, corsHeaders)
    }

    if (url.pathname === '/api/profile/companion' && request.method === 'GET') {
      const payload = await requireUser(request, env)
      const profile = await getUserProfile(env, payload.sub)
      return json({
        name: profile?.companion_name || '小白',
        custom_persona: profile?.custom_persona || '',
        max_persona_length: CUSTOM_PERSONA_MAX_LENGTH,
      }, 200, corsHeaders)
    }

    if (url.pathname === '/api/edge-check/llm' && request.method === 'POST') {
      const payload = await requireUser(request, env)
      const result = await pingLlm(env)
      return json({
        ok: true,
        user_id: payload.sub,
        ...result,
      }, 200, corsHeaders)
    }

    return json({ detail: 'Not found' }, 404, corsHeaders)
  } catch (error) {
    console.error('[workers-api]', error)
    const status = error.status || 500
    return json({ detail: error.message || 'Internal error' }, status, corsHeaders)
  }
}

function getCorsHeaders(request, env) {
  const requestOrigin = request.headers.get('Origin') || ''
  const allowed = (env.ALLOWED_ORIGINS || '')
    .split(',')
    .map(origin => origin.trim())
    .filter(Boolean)

  const allowOrigin = allowed.includes('*')
    ? '*'
    : (allowed.includes(requestOrigin) ? requestOrigin : allowed[0] || requestOrigin)

  return {
    'Access-Control-Allow-Origin': allowOrigin,
    'Access-Control-Allow-Methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
    'Access-Control-Allow-Headers': 'Authorization,Content-Type',
    'Access-Control-Max-Age': '86400',
    'Vary': 'Origin',
  }
}

function json(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      ...headers,
      'Content-Type': 'application/json; charset=utf-8',
    },
  })
}

async function requireUser(request, env) {
  const auth = request.headers.get('Authorization') || ''
  if (!auth.toLowerCase().startsWith('bearer ')) {
    throw httpError(401, '缺少 Authorization header')
  }

  const token = auth.slice(7).trim()
  const payload = await verifySupabaseJwt(token, env)
  if (!payload.sub) {
    throw httpError(401, 'JWT 缺少 sub (user_id)')
  }
  return payload
}

async function verifySupabaseJwt(token, env) {
  const parts = token.split('.')
  if (parts.length !== 3) throw httpError(401, 'JWT 格式错误')

  const header = parseJwtPart(parts[0])
  const payload = parseJwtPart(parts[1])
  const alg = header.alg
  const kid = header.kid
  if (!kid) throw httpError(401, 'JWT 缺少 kid')
  if (!['ES256', 'RS256'].includes(alg)) throw httpError(401, `不支持的 JWT alg: ${alg}`)

  const jwks = await getJwks(env)
  const jwk = jwks.keys?.find(key => key.kid === kid)
  if (!jwk) throw httpError(401, '找不到 JWT 签名公钥')

  const key = await importVerifyKey(jwk, alg)
  const signingInput = new TextEncoder().encode(`${parts[0]}.${parts[1]}`)
  const signature = base64UrlToBytes(parts[2])
  const ok = await crypto.subtle.verify(verifyAlgorithm(alg), key, signature, signingInput)
  if (!ok) throw httpError(401, 'JWT 签名无效')

  const now = Math.floor(Date.now() / 1000)
  if (payload.exp && payload.exp <= now) throw httpError(401, 'JWT 已过期，请重新登录')
  if (payload.nbf && payload.nbf > now) throw httpError(401, 'JWT 尚未生效')

  const expectedAud = env.SUPABASE_JWT_AUDIENCE || 'authenticated'
  const audiences = Array.isArray(payload.aud) ? payload.aud : [payload.aud]
  if (expectedAud && !audiences.includes(expectedAud)) {
    throw httpError(401, 'JWT audience 不匹配')
  }

  if (env.SUPABASE_URL && payload.iss) {
    const expectedIssuer = `${env.SUPABASE_URL.replace(/\/$/, '')}/auth/v1`
    if (payload.iss !== expectedIssuer) {
      throw httpError(401, 'JWT issuer 不匹配')
    }
  }

  return payload
}

async function getJwks(env) {
  const now = Date.now()
  if (jwksCache && now < jwksCacheUntil) return jwksCache

  assertEnv(env, ['SUPABASE_URL'])
  const url = `${env.SUPABASE_URL.replace(/\/$/, '')}/auth/v1/.well-known/jwks.json`
  const resp = await fetch(url)
  if (!resp.ok) throw httpError(500, `JWKS 拉取失败：${resp.status}`)

  jwksCache = await resp.json()
  jwksCacheUntil = now + JWKS_CACHE_TTL_MS
  return jwksCache
}

async function importVerifyKey(jwk, alg) {
  if (alg === 'ES256') {
    return crypto.subtle.importKey(
      'jwk',
      jwk,
      { name: 'ECDSA', namedCurve: 'P-256' },
      false,
      ['verify'],
    )
  }

  return crypto.subtle.importKey(
    'jwk',
    jwk,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,
    ['verify'],
  )
}

function verifyAlgorithm(alg) {
  if (alg === 'ES256') return { name: 'ECDSA', hash: 'SHA-256' }
  return { name: 'RSASSA-PKCS1-v1_5' }
}

function parseJwtPart(part) {
  try {
    return JSON.parse(new TextDecoder().decode(base64UrlToBytes(part)))
  } catch {
    throw httpError(401, 'JWT payload 解析失败')
  }
}

function base64UrlToBytes(value) {
  const normalized = value.replace(/-/g, '+').replace(/_/g, '/')
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')
  const binary = atob(padded)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes
}

async function getUserProfile(env, userId) {
  assertEnv(env, ['SUPABASE_URL', 'SUPABASE_SERVICE_KEY'])
  const baseUrl = env.SUPABASE_URL.replace(/\/$/, '')
  const params = new URLSearchParams({
    user_id: `eq.${userId}`,
    select: 'companion_name,custom_persona',
    limit: '1',
  })

  const resp = await fetch(`${baseUrl}/rest/v1/user_profile?${params}`, {
    headers: supabaseServiceHeaders(env),
  })
  if (!resp.ok) {
    throw httpError(500, `Supabase user_profile 读取失败：${resp.status}`)
  }

  const rows = await resp.json()
  return rows[0] || null
}

async function pingLlm(env) {
  assertEnv(env, ['DEEPSEEK_API_KEY'])
  const baseUrl = env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com'
  const model = env.DEEPSEEK_MODEL || 'deepseek-chat'

  const resp = await fetch(`${baseUrl.replace(/\/$/, '')}/chat/completions`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.DEEPSEEK_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model,
      messages: [
        { role: 'system', content: 'You are a health check endpoint. Reply with exactly: ok' },
        { role: 'user', content: 'ping' },
      ],
      max_tokens: 8,
      temperature: 0,
    }),
  })

  const data = await resp.json().catch(() => null)
  if (!resp.ok) {
    throw httpError(502, `LLM ping 失败：${resp.status}`)
  }

  return {
    provider: 'deepseek',
    model,
    reply: data?.choices?.[0]?.message?.content || '',
  }
}

function supabaseServiceHeaders(env) {
  return {
    'apikey': env.SUPABASE_SERVICE_KEY,
    'Authorization': `Bearer ${env.SUPABASE_SERVICE_KEY}`,
    'Content-Type': 'application/json',
  }
}

function assertEnv(env, names) {
  const missing = names.filter(name => !env[name])
  if (missing.length > 0) {
    throw httpError(500, `Worker 缺少环境变量：${missing.join(', ')}`)
  }
}

function httpError(status, message) {
  const error = new Error(message)
  error.status = status
  return error
}
