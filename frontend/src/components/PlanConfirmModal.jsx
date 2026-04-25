/**
 * 计划确认弹窗 · v5.0 P2（2026-04-22 改）
 *
 * 老版本（P1）：DS 输出 confirmed → 前端调 /api/plan/extract 再提取 → 让用户审核写入
 * 新版本（P2）：DS 直接调 create_tasks 写库 → 本弹窗拿到已写入的任务列表，让用户"事后编辑"
 *
 * 每行可以：
 *   - 改 keyword（onBlur 触发 POST /api/task/{id}/keyword）
 *   - 改时长（chip 点击 / 自定义数字 → POST /api/task/{id}/duration）
 *   - 删除（DELETE /api/task/{id}）
 * 底部只有"关闭"按钮——数据已落库，没有"全部记录"动作可做。
 *
 * initialTasks 结构（从 ChatContext.lastCreatedTasks 来）：
 *   [{ task_id, keyword, minutes, scheduled_at, status }, ...]
 */

import { useState } from 'react'
import { apiFetch } from '../lib/api.js'

const MINUTE_OPTIONS = [25, 45, 60, 90]

export default function PlanConfirmModal({ initialTasks, onClose }) {
  const [tasks, setTasks] = useState(initialTasks || [])
  const [error, setError] = useState(null)

  function patchTask(taskId, patch) {
    setTasks(prev => prev.map(t => t.task_id === taskId ? { ...t, ...patch } : t))
  }

  async function handleChangeKeyword(task, newKw) {
    const keyword = newKw.trim()
    if (!keyword || keyword === task.keyword) return
    patchTask(task.task_id, { keyword })   // 乐观
    try {
      await apiFetch(`/api/task/${task.task_id}/keyword`, {
        method: 'POST',
        body: { keyword },
      })
    } catch (e) {
      patchTask(task.task_id, { keyword: task.keyword })  // 回滚
      setError(`改任务名失败：${e.message}`)
    }
  }

  async function handleChangeMinutes(task, minutes) {
    if (minutes === task.minutes) return
    patchTask(task.task_id, { minutes })
    try {
      await apiFetch(`/api/task/${task.task_id}/duration?minutes=${minutes}`, {
        method: 'POST',
      })
    } catch (e) {
      patchTask(task.task_id, { minutes: task.minutes })
      setError(`改时长失败：${e.message}`)
    }
  }

  async function handleDelete(task) {
    const prev = tasks
    setTasks(prev.filter(t => t.task_id !== task.task_id))
    try {
      await apiFetch(`/api/task/${task.task_id}`, { method: 'DELETE' })
    } catch (e) {
      setTasks(prev)
      setError(`删除失败：${e.message}`)
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
      /* 遮罩点击不关闭 —— 避免用户改任务名时误触丢改动（C-12 方案 A）*/
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
            已帮你记下了这些
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
          任务栏里已经写进去了，这里可以改名、改时长、或者删掉
        </p>

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

          {tasks.length === 0 ? (
            <p style={{
              padding: '40px 20px', textAlign: 'center',
              color: 'var(--color-subtle)', fontSize: 14,
            }}>
              都删光了～
            </p>
          ) : (
            tasks.map(task => (
              <TaskRow
                key={task.task_id}
                task={task}
                onChangeKeyword={kw => handleChangeKeyword(task, kw)}
                onChangeMinutes={m => handleChangeMinutes(task, m)}
                onDelete={() => handleDelete(task)}
              />
            ))
          )}
        </div>

        {/* 底部 */}
        <div style={{
          display: 'flex', justifyContent: 'flex-end',
          paddingTop: 16, marginTop: 8,
          borderTop: '1px solid var(--color-line)',
        }}>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '10px 24px',
              borderRadius: 'var(--radius)',
              border: '1px solid var(--color-primary)',
              background: 'var(--color-primary)', color: '#fff',
              fontSize: 14, fontFamily: 'inherit',
              cursor: 'pointer',
            }}
          >
            好
          </button>
        </div>
      </div>
    </div>
  )
}


// ════════════ 单行任务 ════════════

function TaskRow({ task, onChangeKeyword, onChangeMinutes, onDelete }) {
  const { keyword, minutes } = task
  const [localKw, setLocalKw] = useState(keyword || '')
  const isCustom = minutes != null && !MINUTE_OPTIONS.includes(minutes)

  return (
    <div style={{
      border: '1px solid var(--color-line)',
      borderRadius: 'var(--radius)',
      padding: '14px 16px',
      marginBottom: 10,
      background: 'var(--color-surface)',
      position: 'relative',
    }}>
      <button
        type="button"
        onClick={onDelete}
        title="删除"
        style={{
          position: 'absolute', top: 10, right: 10,
          width: 22, height: 22,
          borderRadius: '50%',
          border: '1px solid var(--color-line)',
          background: 'transparent',
          color: 'var(--color-subtle)',
          fontSize: 13, fontFamily: 'inherit',
          cursor: 'pointer',
          lineHeight: 1,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: 0,
        }}
      >
        ×
      </button>
      {/* keyword */}
      <div style={{ marginBottom: 10, paddingRight: 30 }}>
        <input
          value={localKw}
          onChange={e => setLocalKw(e.target.value)}
          onBlur={() => onChangeKeyword(localKw)}
          onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur() }}
          placeholder="做什么"
          style={{
            width: `${Math.max((localKw.length || 2) + 1, 3)}em`,
            padding: '6px 12px',
            borderRadius: 'var(--radius)',
            border: '1px solid var(--color-line)',
            background: 'var(--color-base)',
            font: 'inherit', color: 'var(--color-text)',
            outline: 'none',
            maxWidth: '100%',
            boxSizing: 'content-box',
          }}
        />
      </div>

      {/* 第二行：时长 chip + 自定义 */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
        {MINUTE_OPTIONS.map(m => (
          <MiniChip
            key={m}
            selected={minutes === m}
            onClick={() => onChangeMinutes(m)}
          >
            {m}m
          </MiniChip>
        ))}
        {isCustom && (
          <MiniChip selected>{minutes}m</MiniChip>
        )}
        <input
          type="number"
          min="1"
          max="480"
          placeholder="自填"
          value=""
          onChange={e => {
            const v = e.target.value
            if (v === '') return
            const n = Math.max(1, Math.min(480, parseInt(v) || 0))
            onChangeMinutes(n)
          }}
          style={{
            width: 52,
            padding: '4px 8px',
            borderRadius: 999,
            border: '1px solid var(--color-line)',
            background: 'transparent',
            color: 'var(--color-text)',
            fontSize: 12, fontFamily: "'Inter', system-ui, sans-serif",
            outline: 'none',
          }}
        />
      </div>
    </div>
  )
}


function MiniChip({ selected, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: '4px 10px',
        borderRadius: 999,
        border: `1px solid ${selected ? 'var(--color-primary)' : 'var(--color-line)'}`,
        background: selected ? 'var(--color-primary-soft)' : 'transparent',
        color: selected ? 'var(--color-primary)' : 'var(--color-subtle)',
        fontSize: 12, fontFamily: "'Inter', system-ui, sans-serif",
        cursor: 'pointer',
        transition: 'var(--transition) ease-out',
      }}
    >
      {children}
    </button>
  )
}
