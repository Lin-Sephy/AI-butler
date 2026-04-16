import { useState } from 'react'

const STATUS_CONFIG = {
  idle: {
    dotStyle: { background: 'transparent', border: '2px solid var(--color-accent)' },
    chipText: null, // 用 task_type (work/rest)
    chipStyle: {
      background: 'var(--color-accent-soft)',
      color: 'var(--color-primary)',
      border: '1px solid var(--color-accent)',
    },
  },
  executing: {
    dotStyle: { background: 'var(--color-primary)' },
    chipText: '进行中',
    chipStyle: {
      background: 'var(--color-primary)',
      color: '#fff',
      border: '1px solid var(--color-primary)',
    },
  },
  paused: {
    dotStyle: { background: 'transparent', border: '2px solid var(--color-accent)' },
    chipText: '已暂停',
    chipStyle: {
      background: 'var(--color-accent-soft)',
      color: 'var(--color-primary)',
      border: '1px solid var(--color-accent)',
    },
  },
  completed: {
    dotStyle: { background: 'var(--color-primary)' },
    chipText: '已完成',
    chipStyle: {
      background: 'hsl(var(--text-h), var(--text-s), 88%)',
      color: 'var(--color-subtle)',
      border: '1px solid hsl(var(--text-h), var(--text-s), 85%)',
    },
  },
}

const TYPE_LABEL = { work: 'work', rest: 'rest' }

export default function TaskCard({ task, onStart, onPause, onResume, onComplete, onAbandon, onDelete }) {
  const [busy, setBusy] = useState(false)
  const status = task.status || 'idle'
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.idle
  const isExecuting = status === 'executing'
  const isCompleted = status === 'completed'

  async function act(fn) {
    if (busy) return
    setBusy(true)
    try { await fn(task.id) } finally { setBusy(false) }
  }

  return (
    <div
      style={{
        background: 'var(--color-surface)',
        borderRadius: 'var(--radius)',
        padding: '18px 22px',
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        marginBottom: 12,
        border: `1px solid ${isExecuting ? 'var(--color-primary)' : 'var(--color-line)'}`,
        borderLeft: isExecuting ? '3px solid var(--color-primary)' : undefined,
        opacity: isCompleted ? 0.7 : 1,
        transition: 'var(--transition) ease-out',
      }}
    >
      {/* Status dot */}
      <div style={{
        width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
        ...cfg.dotStyle,
      }} />

      {/* Body */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 16, fontWeight: 400, marginBottom: 3,
          textDecoration: isCompleted ? 'line-through' : 'none',
          color: isCompleted ? 'var(--color-subtle)' : 'var(--color-text)',
        }}>
          {task.keyword}
        </div>
        <div style={{
          fontSize: 12, color: 'var(--color-subtle)',
          display: 'flex', gap: 10, alignItems: 'center',
          fontFamily: "'Inter', system-ui, sans-serif",
        }}>
          {task.default_minutes && <span>{task.default_minutes} min</span>}
          <span style={{
            padding: '2px 10px',
            borderRadius: 99,
            fontSize: 11,
            ...cfg.chipStyle,
          }}>
            {cfg.chipText || TYPE_LABEL[task.task_type] || task.task_type}
          </span>
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 4 }}>
        {status === 'idle' && (
          <>
            <ActionBtn label="开始" onClick={() => act(onStart)} disabled={busy} />
            <ActionBtn label="删除" onClick={() => act(onDelete)} disabled={busy} subtle />
          </>
        )}
        {status === 'executing' && (
          <>
            <ActionBtn label="暂停" onClick={() => act(onPause)} disabled={busy} />
            <ActionBtn label="完成" onClick={() => act(onComplete)} disabled={busy} />
            <ActionBtn label="放弃" onClick={() => act(onAbandon)} disabled={busy} subtle />
          </>
        )}
        {status === 'paused' && (
          <>
            <ActionBtn label="继续" onClick={() => act(onResume)} disabled={busy} />
            <ActionBtn label="完成" onClick={() => act(onComplete)} disabled={busy} />
            <ActionBtn label="放弃" onClick={() => act(onAbandon)} disabled={busy} subtle />
          </>
        )}
        {status === 'completed' && (
          <ActionBtn label="删除" onClick={() => act(onDelete)} disabled={busy} subtle />
        )}
      </div>
    </div>
  )
}

function ActionBtn({ label, onClick, disabled, subtle }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: '6px 12px',
        borderRadius: 10,
        border: subtle ? '1px solid var(--color-line)' : '1px solid var(--color-primary)',
        background: subtle ? 'transparent' : 'var(--color-primary-soft)',
        color: subtle ? 'var(--color-subtle)' : 'var(--color-primary)',
        fontSize: 12,
        fontFamily: 'inherit',
        cursor: disabled ? 'wait' : 'pointer',
        opacity: disabled ? 0.5 : 1,
        transition: 'var(--transition) ease-out',
      }}
    >
      {label}
    </button>
  )
}
