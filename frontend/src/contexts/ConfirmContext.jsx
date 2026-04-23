/**
 * 全局 ConfirmDialog 系统（C-2）：替换 window.confirm。
 *
 * 用法：
 *   const confirm = useConfirm()
 *   const ok = await confirm('清空吗？')
 *   if (!ok) return
 *
 * 或者传 options：
 *   const ok = await confirm({
 *     message: '清空小白对你的印象？',
 *     confirmText: '清空',
 *     danger: true,
 *   })
 *
 * 挂载：App.jsx 顶层用 <ConfirmProvider> 包住。
 */

import { createContext, useContext, useState, useCallback } from 'react'

const ConfirmContext = createContext(null)

export function ConfirmProvider({ children }) {
  const [state, setState] = useState(null)
  // state: null | { message, confirmText, cancelText, danger, resolve }

  const confirm = useCallback((arg) => {
    const opts = typeof arg === 'string' ? { message: arg } : (arg || {})
    return new Promise((resolve) => {
      setState({
        message: opts.message || '确定吗？',
        confirmText: opts.confirmText || '确定',
        cancelText: opts.cancelText || '取消',
        danger: !!opts.danger,
        resolve,
      })
    })
  }, [])

  function handleConfirm() {
    if (state) state.resolve(true)
    setState(null)
  }
  function handleCancel() {
    if (state) state.resolve(false)
    setState(null)
  }

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {state && (
        <ConfirmDialog
          message={state.message}
          confirmText={state.confirmText}
          cancelText={state.cancelText}
          danger={state.danger}
          onConfirm={handleConfirm}
          onCancel={handleCancel}
        />
      )}
    </ConfirmContext.Provider>
  )
}

export function useConfirm() {
  const confirm = useContext(ConfirmContext)
  if (!confirm) {
    throw new Error('useConfirm 必须在 <ConfirmProvider> 内部使用')
  }
  return confirm
}


// ════════════ Dialog UI ════════════

function ConfirmDialog({ message, confirmText, cancelText, danger, onConfirm, onCancel }) {
  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 200,
        background: 'rgba(0,0,0,0.3)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24,
      }}
      onClick={onCancel}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--color-surface)',
          borderRadius: 'var(--radius)',
          border: '1px solid var(--color-line)',
          padding: '28px 24px',
          width: '100%', maxWidth: 360,
        }}
      >
        <p style={{
          margin: 0,
          marginBottom: 24,
          fontSize: 15,
          color: 'var(--color-text)',
          lineHeight: 1.6,
          whiteSpace: 'pre-wrap',
        }}>
          {message}
        </p>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button
            type="button"
            onClick={onCancel}
            style={{
              padding: '8px 18px',
              borderRadius: 'var(--radius)',
              border: '1px solid var(--color-line)',
              background: 'transparent',
              color: 'var(--color-subtle)',
              fontSize: 14,
              fontFamily: 'inherit',
              cursor: 'pointer',
              transition: 'var(--transition) ease-out',
            }}
          >
            {cancelText}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            autoFocus
            style={{
              padding: '8px 18px',
              borderRadius: 'var(--radius)',
              border: `1px solid ${danger ? '#c04545' : 'var(--color-primary)'}`,
              background: danger ? '#c04545' : 'var(--color-primary)',
              color: '#fff',
              fontSize: 14,
              fontFamily: 'inherit',
              cursor: 'pointer',
              transition: 'var(--transition) ease-out',
            }}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  )
}
