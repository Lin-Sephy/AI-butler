/**
 * 删除确认弹窗
 *
 * DS 调 delete_task(s) 后不真删，把待删列表传到前端。
 * 本弹窗展示列表，用户勾选确认后才真正调 DELETE /api/task/{id} 删除。
 *
 * pendingTasks 结构（从 ChatContext.pendingDeletes 来）：
 *   [{ task_id, keyword, status, minutes }, ...]
 */

import { useState } from 'react'
import { apiFetch } from '../lib/api.js'

const STATUS_LABEL = {
  idle: '待完成',
  executing: '进行中',
  paused: '已暂停',
  scheduled: '已预定',
  completed: '已完成',
  abandoned: '已放弃',
}

export default function DeleteConfirmModal({ pendingTasks, onClose, onDeleted }) {
  const [selected, setSelected] = useState(() => new Set(pendingTasks.map(t => t.task_id)))
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState(null)

  function toggle(taskId) {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(taskId)) next.delete(taskId)
      else next.add(taskId)
      return next
    })
  }

  function toggleAll() {
    if (selected.size === pendingTasks.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(pendingTasks.map(t => t.task_id)))
    }
  }

  async function handleConfirm() {
    if (selected.size === 0) { onClose(); return }
    setDeleting(true)
    setError(null)
    const failed = []
    for (const tid of selected) {
      try {
        await apiFetch(`/api/task/${tid}`, { method: 'DELETE' })
      } catch (e) {
        failed.push(tid)
      }
    }
    setDeleting(false)
    if (failed.length > 0) {
      setError(`${failed.length} 条删除失败，请重试`)
    } else {
      if (onDeleted) onDeleted()
      onClose()
    }
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 100,
        background: 'rgba(0,0,0,0.3)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--color-surface)',
          borderRadius: 'var(--radius)',
          border: '1px solid var(--color-line)',
          padding: '28px 24px',
          width: '100%', maxWidth: 520,
          maxHeight: '80vh',
          display: 'flex', flexDirection: 'column',
        }}
      >
        {/* 头部 */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
          marginBottom: 6,
        }}>
          <h2 style={{ fontSize: 20, fontWeight: 400, margin: 0 }}>
            小白想删这些任务
          </h2>
          <button
            type="button"
            onClick={onClose}
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
        <p style={{ fontSize: 12, color: 'var(--color-subtle)', marginBottom: 18 }}>
          勾选要删的，取消勾选的会保留
        </p>

        {/* 全选 */}
        <label style={{
          display: 'flex', alignItems: 'center', gap: 8,
          fontSize: 13, color: 'var(--color-subtle)',
          marginBottom: 12, cursor: 'pointer',
        }}>
          <input
            type="checkbox"
            checked={selected.size === pendingTasks.length}
            onChange={toggleAll}
          />
          全选 ({selected.size}/{pendingTasks.length})
        </label>

        {/* 主体 */}
        <div style={{ flex: 1, overflowY: 'auto', paddingRight: 4 }}>
          {error && (
            <div style={{
              padding: '10px 14px', marginBottom: 12,
              borderRadius: 'var(--radius)',
              background: '#fee', border: '1px solid #fbb',
              fontSize: 13, color: '#933',
            }}>
              {error}
            </div>
          )}

          {pendingTasks.map(task => (
            <label
              key={task.task_id}
              style={{
                display: 'flex', alignItems: 'center', gap: 12,
                border: '1px solid var(--color-line)',
                borderRadius: 'var(--radius)',
                padding: '14px 16px',
                marginBottom: 10,
                background: selected.has(task.task_id) ? 'var(--color-accent-soft)' : 'var(--color-surface)',
                cursor: 'pointer',
                transition: 'var(--transition) ease-out',
              }}
            >
              <input
                type="checkbox"
                checked={selected.has(task.task_id)}
                onChange={() => toggle(task.task_id)}
              />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 15, color: 'var(--color-text)' }}>
                  {task.keyword}
                </div>
                <div style={{ fontSize: 12, color: 'var(--color-subtle)', marginTop: 2 }}>
                  {STATUS_LABEL[task.status] || task.status}
                  {task.minutes ? ` · ${task.minutes}分钟` : ''}
                </div>
              </div>
            </label>
          ))}
        </div>

        {/* 底部 */}
        <div style={{
          display: 'flex', justifyContent: 'flex-end', gap: 12,
          paddingTop: 16, marginTop: 8,
          borderTop: '1px solid var(--color-line)',
        }}>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '10px 24px',
              borderRadius: 'var(--radius)',
              border: '1px solid var(--color-line)',
              background: 'var(--color-surface)', color: 'var(--color-text)',
              fontSize: 14, fontFamily: 'inherit',
              cursor: 'pointer',
            }}
          >
            全部保留
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={deleting}
            style={{
              padding: '10px 24px',
              borderRadius: 'var(--radius)',
              border: '1px solid #d44',
              background: '#d44', color: '#fff',
              fontSize: 14, fontFamily: 'inherit',
              cursor: deleting ? 'wait' : 'pointer',
              opacity: deleting ? 0.6 : 1,
            }}
          >
            {deleting ? '删除中…' : `确认删除 (${selected.size})`}
          </button>
        </div>
      </div>
    </div>
  )
}
