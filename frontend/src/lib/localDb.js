import Dexie from 'dexie'

const DB_NAME = 'ai-butler-local-db'
export const DB_SCHEMA_VERSION = 1
export const SESSION_CACHE_LIMIT = 20

export const db = new Dexie(DB_NAME)

db.version(DB_SCHEMA_VERSION).stores({
  meta: '&key',
  settings: '&key, updated_at',
  sessions: '&id, updated_at',
  chat_messages: '++id, session_id, timestamp',
  tasks: '&id, task_id, status, updated_at, sync_status',
  recent_events: '++id, type, created_at',
})

export async function initLocalDb() {
  await db.open()
  const existing = await db.meta.get('schema_version')
  if (existing?.value !== DB_SCHEMA_VERSION) {
    await db.close()
    await Dexie.delete(DB_NAME)
    await db.open()
    await db.meta.put({ key: 'schema_version', value: DB_SCHEMA_VERSION })
  }
}

function normalizeMessage(message, sessionId) {
  const parsedTimestamp = typeof message.timestamp === 'string'
    ? Date.parse(message.timestamp)
    : message.timestamp
  return {
    session_id: sessionId,
    role: message.role,
    content: message.content,
    mode: message.mode || 'chat',
    timestamp: Number.isFinite(parsedTimestamp) ? parsedTimestamp : Date.now(),
  }
}

function normalizeSession(session) {
  const sessionId = session?.session_id || session?.id
  if (!sessionId) return null
  return {
    ...session,
    id: sessionId,
    session_id: sessionId,
    title: session.title || '未命名对话',
    latest_at: session.latest_at || '',
    updated_at: Date.now(),
  }
}

function sortSessions(sessions) {
  return [...sessions].sort((a, b) => {
    const aKey = a.latest_at || String(a.updated_at || '')
    const bKey = b.latest_at || String(b.updated_at || '')
    return bKey.localeCompare(aKey)
  })
}

export async function loadCachedSessions(limit = SESSION_CACHE_LIMIT) {
  const rows = await db.sessions.toArray()
  return sortSessions(rows).slice(0, limit)
}

export async function saveCachedSessions(sessions, limit = SESSION_CACHE_LIMIT) {
  const rows = (sessions || [])
    .map(normalizeSession)
    .filter(Boolean)
  const keepRows = sortSessions(rows).slice(0, limit)
  const keepIds = new Set(keepRows.map(row => row.id))

  await db.transaction('rw', db.sessions, db.chat_messages, async () => {
    if (keepRows.length > 0) {
      await db.sessions.bulkPut(keepRows)
    }

    const existing = await db.sessions.toArray()
    const staleIds = existing
      .map(row => row.id)
      .filter(id => id && !keepIds.has(id))

    if (staleIds.length > 0) {
      await db.sessions.bulkDelete(staleIds)
      await Promise.all(staleIds.map(id => (
        db.chat_messages.where('session_id').equals(id).delete()
      )))
    }
  })
}

export async function loadSessionMessages(sessionId) {
  if (!sessionId) return []
  return db.chat_messages
    .where('session_id')
    .equals(sessionId)
    .sortBy('timestamp')
}

export async function saveSessionMessages(sessionId, messages) {
  if (!sessionId) return
  const rows = (messages || []).map((msg, index) => normalizeMessage({
    ...msg,
    timestamp: msg.timestamp ?? Date.now() + index,
  }, sessionId))

  await db.transaction('rw', db.chat_messages, async () => {
    await db.chat_messages.where('session_id').equals(sessionId).delete()
    if (rows.length > 0) {
      await db.chat_messages.bulkAdd(rows)
    }
  })
}

export async function addSessionMessage(sessionId, message) {
  if (!sessionId || !message?.role || !message?.content) return
  return db.chat_messages.add(normalizeMessage(message, sessionId))
}

export async function clearSessionMessages(sessionId) {
  if (!sessionId) return
  return db.chat_messages.where('session_id').equals(sessionId).delete()
}

export async function getSetting(key) {
  return db.settings.get(key)
}

export async function setSetting(key, value) {
  return db.settings.put({ key, value, updated_at: Date.now() })
}

export async function getTasks() {
  return db.tasks.toArray()
}

export async function upsertTask(task) {
  if (!task?.id) return
  return db.tasks.put({
    ...task,
    updated_at: task.updated_at ?? Date.now(),
  })
}

export async function getRecentEvents() {
  return db.recent_events.orderBy('created_at').reverse().toArray()
}

export async function addRecentEvent(event) {
  return db.recent_events.add({
    ...event,
    created_at: Date.now(),
  })
}
