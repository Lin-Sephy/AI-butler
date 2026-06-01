/**
 * 设置面板 · v5.0（2026-04-21）
 *
 * Modal，follow NewTaskModal 的 padding / 遮罩 / 关闭模式。
 * 六个区块：命名 / 性格 / 日常作息 / 用户手记 / AI 记忆 / API key。
 *
 * 保存策略：底部一个总"保存"按钮；关闭前如有 dirty 字段弹 confirm。
 * AI 记忆的"清空"是独立动作（不受总保存管）。
 * max_length 全部从 API 返回值读，不 hardcode。
 */

import { useCallback, useEffect, useState, useRef } from 'react'
import { apiFetch } from '../lib/api.js'
import { useConfirm } from '../contexts/ConfirmContext.jsx'
import { useToast } from '../contexts/ToastContext.jsx'
import { useChat } from '../contexts/ChatContext.jsx'
import { recordSessionNote } from '../lib/chatApi.js'
import { initLocalDb, getSetting, setSetting } from '../lib/localDb.js'
import PersonaPresets from './PersonaPresets.jsx'
import LlmConfig from './LlmConfig.jsx'
import ErrorBanner from './ErrorBanner.jsx'

export default function SettingsPanel({ onClose }) {
  const confirm = useConfirm()
  const showToast = useToast()
  const { sessionId, setCompanionName } = useChat()
  // ─── 可编辑字段（受 dirty 跟踪） ───
  const [name, setName] = useState('')
  const [persona, setPersona] = useState('')
  const [routine, setRoutine] = useState('')
  const [userMemo, setUserMemo] = useState('')

  // 初始值快照，用于 dirty 检查；savedRef 表示上次已保存/缓存的值
  const savedRef = useRef({ name: '', persona: '', routine: '', userMemo: '' })

  // max_length（从各 API 读）
  const [personaMax, setPersonaMax] = useState(1000)
  const [routineMax, setRoutineMax] = useState(500)
  const [memoMax, setMemoMax] = useState(2000)

  // AI 记忆（只读）
  const [aiMemo, setAiMemo] = useState('')
  const [aiMemoLoading, setAiMemoLoading] = useState(false)

  // 状态
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [savedHint, setSavedHint] = useState(false)

  // ─── 首次加载：并行拉 4 个 GET（persona_presets 由 PersonaPresets 子组件自己拉） ───
  const loadAll = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      await initLocalDb()

      // 1) 先从本地缓存读并显示（无论是否存在）
      try {
        const companionRec = await getSetting('companion')
        const routineRec = await getSetting('daily_routine')
        const userMemoRec = await getSetting('user_memo')
        const aiMemoRec = await getSetting('ai_memo')

        const cachedCompanion = companionRec?.value || {}
        const cachedRoutine = routineRec?.value || {}
        const cachedUserMemo = userMemoRec?.value || {}
        const cachedAiMemo = aiMemoRec?.value || {}

        const cachedName = cachedCompanion.name || ''
        const cachedPersona = cachedCompanion.custom_persona || ''
        setName(cachedName)
        setCompanionName(cachedName)
        setPersona(cachedPersona)
        setPersonaMax(cachedCompanion.max_persona_length ?? 1000)

        setRoutine(cachedRoutine.routine || '')
        setRoutineMax(cachedRoutine.max_length ?? 500)

        setUserMemo(cachedUserMemo.content || '')
        setMemoMax(cachedUserMemo.max_length ?? 2000)

        setAiMemo(cachedAiMemo.content || '')

        savedRef.current = {
          name: cachedName,
          persona: cachedPersona,
          routine: cachedRoutine.routine || '',
          userMemo: cachedUserMemo.content || '',
        }
      } catch (e) {
        // 本地缓存读失败不致命，继续拉后端
        console.warn('读取本地缓存失败', e)
      }

      // 2) 后台并行拉取后端最新，并做字段级合并
      const [companion, routineData, memoData, aiMemoData] = await Promise.all([
        apiFetch('/api/profile/companion'),
        apiFetch('/api/profile/daily_routine'),
        apiFetch('/api/memo/user'),
        apiFetch('/api/memo/ai'),
      ])

      const companionName = companion.name || ''
      const backendPersona = companion.custom_persona || ''
      const backendPersonaMax = companion.max_persona_length ?? 1000

      // 字段级合并：只有当用户没有在编辑（draft === saved）时才覆盖 draft
      if (name === savedRef.current.name) {
        setName(companionName)
        setCompanionName(companionName)
      }
      if (persona === savedRef.current.persona) setPersona(backendPersona)
      setPersonaMax(backendPersonaMax)

      if (routine === savedRef.current.routine) setRoutine(routineData.routine || '')
      setRoutineMax(routineData.max_length ?? 500)

      if (userMemo === savedRef.current.userMemo) setUserMemo(memoData.content || '')
      setMemoMax(memoData.max_length ?? 2000)

      // AI 记忆展示：非编辑区，直接更新
      setAiMemo(aiMemoData.content || '')

      // 更新本地缓存为后端权威值（覆盖本地缓存）
      try {
        await setSetting('companion', { name: companionName, custom_persona: backendPersona, max_persona_length: backendPersonaMax })
        await setSetting('daily_routine', { routine: routineData.routine || '', max_length: routineData.max_length ?? 500 })
        await setSetting('user_memo', { content: memoData.content || '', max_length: memoData.max_length ?? 2000 })
        await setSetting('ai_memo', { content: aiMemoData.content || '' })
      } catch (e) {
        console.warn('写本地缓存失败', e)
      }

      // 更新 savedRef 快照（已保存/后端值）
      savedRef.current = {
        name: companionName,
        persona: backendPersona,
        routine: routineData.routine || '',
        userMemo: memoData.content || '',
      }
    } catch (e) {
      setLoadError(e.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [setCompanionName])

  useEffect(() => { loadAll() }, [loadAll])

  // ─── dirty 判断 ───
  function isDirty() {
    const o = savedRef.current
    return name !== o.name || persona !== o.persona
        || routine !== o.routine || userMemo !== o.userMemo
  }

  // ─── 关闭（检查 dirty） ───
  async function handleClose() {
    if (isDirty()) {
      if (!await confirm('有改动没保存，确定关闭？')) return
    }
    onClose()
  }

  // ─── 保存：逐个 PUT/POST 只传改动的字段 ───
  async function handleSave() {
    if (saving) return
    setSaving(true)
    setSaveError(null)

    const o = savedRef.current

    // 先把草稿写到本地缓存，保护用户输入
    try {
      await setSetting('companion', { name, custom_persona: persona, max_persona_length: personaMax })
      await setSetting('daily_routine', { routine, max_length: routineMax })
      await setSetting('user_memo', { content: userMemo, max_length: memoMax })
    } catch (e) {
      console.warn('写本地缓存失败', e)
    }

    const jobs = []  // { label, promise, apply }

    // companion 有 name 和 custom_persona 两字段，一次 PUT 传改动过的
    const companionPatch = {}
    if (name !== o.name) companionPatch.name = name
    if (persona !== o.persona) companionPatch.custom_persona = persona
    if (Object.keys(companionPatch).length > 0) {
      jobs.push({
        label: '名字/性格',
        promise: apiFetch('/api/profile/companion', { method: 'PUT', body: companionPatch }),
        apply: snap => {
          const oldName = snap.name || '小白'
          // apply 使用后端返回值为准，但也保留用户输入的语义
          snap.name = companionPatch.name ?? snap.name
          snap.persona = companionPatch.custom_persona ?? snap.persona
          if (Object.prototype.hasOwnProperty.call(companionPatch, 'name')) {
            setCompanionName(companionPatch.name)
            if (sessionId) {
              recordSessionNote({
                sessionId,
                mode: 'chat',
                content: `用户把跟宠名字从「${oldName}」改成了「${companionPatch.name}」。以后请用「${companionPatch.name}」自称或回应相关称呼。`,
              }).catch(e => {
                showToast(`名字已保存，但没有通知到跟宠：${e.message}`)
              })
            }
          }
        },
      })
    }
    if (routine !== o.routine) {
      jobs.push({
        label: '日常作息',
        promise: apiFetch('/api/profile/daily_routine', { method: 'PUT', body: { routine } }),
        apply: snap => { snap.routine = routine },
      })
    }
    if (userMemo !== o.userMemo) {
      jobs.push({
        label: '手记',
        promise: apiFetch('/api/memo/user', { method: 'POST', body: { content: userMemo } }),
        apply: snap => { snap.userMemo = userMemo },
      })
    }

    // allSettled：部分字段失败不影响其他字段入库；快照只更新成功的，让失败字段继续显示"待保存"
    const results = await Promise.allSettled(jobs.map(j => j.promise))
    const nextSnap = { ...o }
    const failed = []
    results.forEach((r, i) => {
      if (r.status === 'fulfilled') jobs[i].apply(nextSnap)
      else failed.push({ label: jobs[i].label, reason: r.reason?.message })
    })

    // 更新本地缓存为后端权威（或用户已写入的值）
    try {
      await setSetting('companion', { name: nextSnap.name, custom_persona: nextSnap.persona, max_persona_length: personaMax })
      await setSetting('daily_routine', { routine: nextSnap.routine, max_length: routineMax })
      await setSetting('user_memo', { content: nextSnap.userMemo, max_length: memoMax })
    } catch (e) {
      console.warn('写本地缓存失败', e)
    }

    savedRef.current = nextSnap

    if (failed.length === 0) {
      setSavedHint(true)
      setTimeout(() => setSavedHint(false), 1500)
    } else {
      setSaveError(`部分没存上：${failed.map(f => `${f.label}（${f.reason || '未知错误'}）`).join('，')}`)
    }
    setSaving(false)
  }

  // ─── 清空 AI 记忆 ───
  async function handleClearAiMemo() {
    if (!await confirm({
      message: '清空跟宠对你的印象？这个不可撤销。',
      confirmText: '清空',
      danger: true,
    })) return
    setAiMemoLoading(true)
    try {
      await apiFetch('/api/memo/ai', { method: 'DELETE' })
      setAiMemo('')
      try { await setSetting('ai_memo', { content: '' }) } catch (e) { console.warn('更新本地 ai_memo 失败', e) }
    } catch (e) {
      showToast(`清空失败：${e.message}`)
    } finally {
      setAiMemoLoading(false)
    }
  }

  // ─── 渲染 ───
  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 100,
        background: 'rgba(0,0,0,0.3)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24,
      }}
      onClick={handleClose}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--color-surface)',
          borderRadius: 'var(--radius)',
          border: '1px solid var(--color-line)',
          padding: '28px 24px',
          width: '100%', maxWidth: 480,
          maxHeight: '80vh',
          display: 'flex', flexDirection: 'column',
        }}
      >
        {/* 头部 */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
          marginBottom: 20,
        }}>
          <h2 style={{ fontSize: 20, fontWeight: 400, margin: 0 }}>设置</h2>
          <button
            type="button"
            onClick={handleClose}
            style={{
              background: 'transparent', border: 'none',
              fontSize: 22, color: 'var(--color-subtle)',
              cursor: 'pointer', padding: 0, lineHeight: 1,
              fontFamily: 'inherit',
            }}
            title="关闭"
          >
            ×
          </button>
        </div>

        {/* 滚动区 */}
        <div style={{ flex: 1, overflowY: 'auto', paddingRight: 4 }}>
          {loading ? (
            <div style={{
              color: 'var(--color-subtle)', fontSize: 14,
              padding: '40px 0', textAlign: 'center',
            }}>
              加载中…
            </div>
          ) : loadError ? (
            <div>
              <ErrorBanner>{loadError}</ErrorBanner>
              <p style={{ fontSize: 13, color: 'var(--color-subtle)', marginBottom: 12 }}>
                可能是网络波动，重试一下试试。
              </p>
              <button
                type="button"
                onClick={loadAll}
                style={primaryBtnStyle}
              >
                重试
              </button>
            </div>
          ) : (
            <>
              {/* ① 跟宠命名 */}
              <Section title="跟宠命名" hint="给跟宠起个名字">
                <input
                  value={name}
                  onChange={e => setName(e.target.value)}
                  maxLength={20}
                  placeholder="给跟宠起个名字"
                  style={inputStyle}
                />
              </Section>

              {/* ② 性格 */}
              <Section title="性格" hint="可以从预设里挑一个再改，也可以自己写">
                <PersonaPresets
                  currentText={persona}
                  onPick={text => setPersona(text)}
                />
                <textarea
                  value={persona}
                  onChange={e => setPersona(e.target.value)}
                  maxLength={personaMax}
                  placeholder="写写希望跟宠是什么样的人"
                  rows={6}
                  style={textareaStyle}
                />
                <CharCount current={persona.length} max={personaMax} />
              </Section>

              {/* ③ 日常作息 */}
              <Section title="日常作息" hint="跟宠会参考，随时可以改">
                <textarea
                  value={routine}
                  onChange={e => setRoutine(e.target.value)}
                  maxLength={routineMax}
                  placeholder="例：9:00 开始学习；12:00-15:00 休息；18:00-19:00 吃饭；22:00 休息"
                  rows={3}
                  style={textareaStyle}
                />
                <CharCount current={routine.length} max={routineMax} />
              </Section>

              {/* ④ 用户手记 */}
              <Section title="用户手记" hint="你想让跟宠知道的事，可以都写在这里">
                <textarea
                  value={userMemo}
                  onChange={e => setUserMemo(e.target.value)}
                  maxLength={memoMax}
                  placeholder="最近在忙什么、有什么想法、哪些事不想被提起……"
                  rows={5}
                  style={textareaStyle}
                />
                <CharCount current={userMemo.length} max={memoMax} />
              </Section>

              {/* ⑤ AI 记忆 */}
              <Section
                title="跟宠对你的印象"
                hint="跟宠从对话里慢慢记下来的"
                action={
                  <button
                    type="button"
                    disabled={aiMemoLoading || !aiMemo}
                    onClick={handleClearAiMemo}
                    style={linkBtnStyle(aiMemoLoading || !aiMemo)}
                  >
                    清空
                  </button>
                }
              >
                <textarea
                  value={aiMemo || '还在慢慢了解你呢'}
                  readOnly
                  rows={4}
                  style={{
                    ...textareaStyle,
                    background: 'var(--color-base)',
                    color: aiMemo ? 'var(--color-text)' : 'var(--color-subtle)',
                    cursor: 'default',
                  }}
                />
              </Section>

              {/* ⑥ API key（BYOK） */}
              <Section title="API key" hint="自带 key 用自己的模型；不填默认 DeepSeek">
                <LlmConfig />
              </Section>
            </>
          )}
        </div>

        {/* 底部操作 */}
        {!loading && !loadError && (
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
            gap: 12, paddingTop: 16, marginTop: 8,
            borderTop: '1px solid var(--color-line)',
          }}>
            {saveError && (
              <span style={{ fontSize: 12, color: '#933', flex: 1 }}>{saveError}</span>
            )}
            {savedHint && !saveError && (
              <span style={{ fontSize: 12, color: 'var(--color-subtle)', flex: 1 }}>已保存</span>
            )}
            <button
              type="button"
              onClick={handleClose}
              style={secondaryBtnStyle}
            >
              关闭
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || !isDirty()}
              style={{
                ...primaryBtnStyle,
                cursor: saving ? 'wait' : (isDirty() ? 'pointer' : 'not-allowed'),
                opacity: (saving || !isDirty()) ? 0.5 : 1,
              }}
            >
              {saving ? '保存中…' : '保存'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}


// ════════════ 子组件：区块 ════════════

function Section({ title, hint, action, children }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
        marginBottom: 6,
      }}>
        <div>
          <div style={{ fontSize: 15, color: 'var(--color-text)' }}>{title}</div>
          {hint && (
            <div style={{ fontSize: 12, color: 'var(--color-subtle)', marginTop: 2 }}>
              {hint}
            </div>
          )}
        </div>
        {action}
      </div>
      <div style={{ marginTop: 8 }}>
        {children}
      </div>
    </div>
  )
}

function CharCount({ current, max }) {
  const near = current > max * 0.9
  return (
    <div style={{
      fontSize: 11,
      color: near ? 'var(--color-primary)' : 'var(--color-subtle)',
      textAlign: 'right',
      marginTop: 4,
      fontFamily: "'Inter', system-ui, sans-serif",
    }}>
      {current} / {max}
    </div>
  )
}



// ════════════ 公共样式 ════════════

const inputStyle = {
  width: '100%',
  padding: '10px 14px',
  borderRadius: 'var(--radius)',
  border: '1px solid var(--color-line)',
  background: 'var(--color-surface)',
  font: 'inherit',
  color: 'var(--color-text)',
  outline: 'none',
  boxSizing: 'border-box',
}

const textareaStyle = {
  ...inputStyle,
  padding: '10px 14px',
  resize: 'vertical',
  lineHeight: 1.55,
  fontFamily: 'inherit',
}

const primaryBtnStyle = {
  padding: '10px 24px',
  borderRadius: 'var(--radius)',
  border: '1px solid var(--color-primary)',
  background: 'var(--color-primary)',
  color: '#fff',
  fontSize: 14, fontFamily: 'inherit',
  cursor: 'pointer',
}

const secondaryBtnStyle = {
  padding: '10px 20px',
  borderRadius: 'var(--radius)',
  border: '1px solid var(--color-line)',
  background: 'transparent',
  color: 'var(--color-subtle)',
  fontSize: 14, fontFamily: 'inherit',
  cursor: 'pointer',
}

function linkBtnStyle(disabled) {
  return {
    padding: '4px 10px',
    borderRadius: 10,
    border: '1px solid var(--color-line)',
    background: 'transparent',
    color: disabled ? 'var(--color-line)' : 'var(--color-subtle)',
    fontSize: 12, fontFamily: 'inherit',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1,
  }
}
