import { createContext, useContext, useState, useCallback, useRef } from 'react'

const ToastContext = createContext(null)

export function useToast() {
  return useContext(ToastContext)
}

export function ToastProvider({ children }) {
  const [toast, setToast] = useState(null)
  const timerRef = useRef(null)

  const showToast = useCallback((msg, duration = 3000) => {
    clearTimeout(timerRef.current)
    setToast(msg)
    timerRef.current = setTimeout(() => setToast(null), duration)
  }, [])

  return (
    <ToastContext.Provider value={showToast}>
      {children}
      {toast && (
        <div style={{
          position: 'fixed',
          bottom: 80, left: '50%', transform: 'translateX(-50%)',
          zIndex: 300,
          padding: '10px 20px',
          borderRadius: 'var(--radius)',
          background: '#fee', border: '1px solid #fbb',
          color: '#933', fontSize: 13,
          boxShadow: '0 2px 12px rgba(0,0,0,0.08)',
          maxWidth: 'calc(100vw - 48px)',
          textAlign: 'center',
          animation: 'toastIn 300ms ease-out',
        }}>
          {toast}
        </div>
      )}
    </ToastContext.Provider>
  )
}
