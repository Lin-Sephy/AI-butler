import { useState } from 'react'
import { useConfirm } from '../contexts/ConfirmContext.jsx'

const MINUTE_OPTIONS = [25, 35, 45, 60, 90, 120]

export default function NewTaskModal({ onSubmit, onClose }) {
  const confirm = useConfirm()
  const [keyword, setKeyword] = useState('')
  const [minutes, setMinutes] = useState(25)
  const [customMinutes, setCustomMinutes] = useState('')
  const [useCustom, setUseCustom] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [recurring, setRecurring] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!keyword.trim() || submitting) return
    setSubmitting(true)
    const finalMinutes = useCustom ? (parseInt(customMinutes) || 25) : minutes
    try {
      await onSubmit({
        task_keyword: keyword.trim(),
        suggested_minutes: finalMinutes,
        recurring,
      })
      onClose()
    } finally {
      setSubmitting(false)
    }
  }

  // 遮罩点击：keyword 已填则 confirm 再关，避免误触丢输入（C-12）
  async function handleBackdropClick() {
    if (keyword.trim() && !await confirm('还没提交，确定关掉吗？')) return
    onClose()
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 100,
        background: 'rgba(0,0,0,0.3)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24,
      }}
      onClick={handleBackdropClick}
    >
      <form
        onClick={e => e.stopPropagation()}
        onSubmit={handleSubmit}
        style={{
          background: 'var(--color-surface)',
          borderRadius: 'var(--radius)',
          border: '1px solid var(--color-line)',
          padding: '28px 24px',
          width: '100%', maxWidth: 420,
        }}
      >
        <h2 style={{ fontSize: 20, fontWeight: 400, marginBottom: 20 }}>
          新建任务
        </h2>

        {/* Keyword */}
        <label style={{ fontSize: 13, color: 'var(--color-subtle)', display: 'block', marginBottom: 6 }}>
          做什么？
        </label>
        <input
          autoFocus
          value={keyword}
          onChange={e => setKeyword(e.target.value)}
          placeholder="给自己安排点什么"
          style={{
            width: '100%', padding: '12px 16px',
            borderRadius: 'var(--radius)',
            border: '1px solid var(--color-line)',
            background: 'var(--color-surface)',
            font: 'inherit', color: 'var(--color-text)',
            marginBottom: 16,
          }}
        />

        {/* Minutes */}
        <label style={{ fontSize: 13, color: 'var(--color-subtle)', display: 'block', marginBottom: 6 }}>
          时长
        </label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
          {MINUTE_OPTIONS.map(m => (
            <button
              key={m}
              type="button"
              onClick={() => { setMinutes(m); setUseCustom(false) }}
              style={{
                padding: '6px 14px',
                borderRadius: 'var(--radius)',
                border: `1px solid ${!useCustom && m === minutes ? 'var(--color-primary)' : 'var(--color-line)'}`,
                background: !useCustom && m === minutes ? 'var(--color-primary-soft)' : 'transparent',
                color: !useCustom && m === minutes ? 'var(--color-primary)' : 'var(--color-subtle)',
                fontSize: 13, fontFamily: "'Inter', system-ui, sans-serif",
                cursor: 'pointer',
              }}
            >
              {m} min
            </button>
          ))}
          <div style={{
            display: 'flex', alignItems: 'center',
            padding: '6px 14px',
            borderRadius: 'var(--radius)',
            border: `1px solid ${useCustom ? 'var(--color-primary)' : 'var(--color-line)'}`,
            background: useCustom ? 'var(--color-primary-soft)' : 'transparent',
            gap: 2,
          }}>
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              placeholder="自填"
              value={customMinutes}
              onFocus={() => setUseCustom(true)}
              onChange={e => {
                const v = e.target.value.replace(/\D/g, '')
                setCustomMinutes(v)
                setUseCustom(true)
              }}
              style={{
                width: 40, padding: 0,
                border: 'none', background: 'transparent',
                fontSize: 13, fontFamily: "'Inter', system-ui, sans-serif",
                color: useCustom ? 'var(--color-primary)' : 'var(--color-text)',
                outline: 'none',
              }}
            />
            <span style={{
              fontSize: 13, fontFamily: "'Inter', system-ui, sans-serif",
              color: useCustom ? 'var(--color-primary)' : 'var(--color-subtle)',
            }}>min</span>
          </div>
        </div>

        {/* 每日循环 */}
        <label style={{
          display: 'flex', alignItems: 'center', gap: 8,
          fontSize: 13, cursor: 'pointer', marginBottom: 24,
        }}
          onClick={() => setRecurring(!recurring)}
        >
          <div style={{
            width: 34, height: 18,
            borderRadius: 999,
            border: `1px solid ${recurring ? 'var(--color-primary)' : 'var(--color-line)'}`,
            background: recurring ? 'var(--color-primary)' : 'var(--color-accent-soft)',
            position: 'relative',
            transition: 'background var(--transition) ease-out, border-color var(--transition) ease-out',
            flexShrink: 0,
          }}>
            <span style={{
              position: 'absolute',
              top: 1, left: recurring ? 17 : 1,
              width: 14, height: 14,
              borderRadius: '50%',
              background: '#fff',
              transition: 'left var(--transition) ease-out',
              boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
            }} />
          </div>
          每日循环
          {recurring && <span style={{ fontSize: 12, color: 'var(--color-subtle)' }}>每天自动出现</span>}
        </label>

        {/* Submit / Cancel */}
        <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '10px 20px', borderRadius: 'var(--radius)',
              border: '1px solid var(--color-line)', background: 'transparent',
              color: 'var(--color-subtle)', fontSize: 14, fontFamily: 'inherit', cursor: 'pointer',
            }}
          >
            取消
          </button>
          <button
            type="submit"
            disabled={!keyword.trim() || submitting}
            style={{
              padding: '10px 24px', borderRadius: 'var(--radius)',
              border: '1px solid var(--color-primary)',
              background: 'var(--color-primary)', color: '#fff',
              fontSize: 14, fontFamily: 'inherit',
              cursor: submitting ? 'wait' : 'pointer',
              opacity: !keyword.trim() || submitting ? 0.5 : 1,
            }}
          >
            {submitting ? '记录中…' : '记录'}
          </button>
        </div>
      </form>
    </div>
  )
}
