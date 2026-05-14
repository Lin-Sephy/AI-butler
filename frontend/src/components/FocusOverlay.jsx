import { useState, useEffect, useRef } from 'react'

export default function FocusOverlay({ task, onComplete, onAbandon }) {
  const initialStartTime = parseTaskTime(task.started_at) || Date.now()
  const initialElapsed = Math.max(0, Math.floor((Date.now() - initialStartTime) / 1000))
  const [elapsed, setElapsed] = useState(initialElapsed)
  const [paused, setPaused] = useState(false)
  const [tooShortHint, setTooShortHint] = useState(false)
  const intervalRef = useRef(null)
  // 以 Date.now() 为基准，避免 tab 不可见时 setInterval 被浏览器节流导致秒数丢失
  const startTimeRef = useRef(initialStartTime)
  const pausedAccumRef = useRef(0) // 累计暂停毫秒
  const pauseStartRef = useRef(null) // 当前暂停段起点，未暂停时为 null

  const totalSeconds = (task.default_minutes || 25) * 60
  const isCountdown = !!task.default_minutes
  const remaining = Math.max(0, totalSeconds - elapsed)

  // 暂停状态切换时维护累计暂停时长
  useEffect(() => {
    if (paused) {
      pauseStartRef.current = Date.now()
    } else if (pauseStartRef.current !== null) {
      pausedAccumRef.current += Date.now() - pauseStartRef.current
      pauseStartRef.current = null
    }
  }, [paused])

  useEffect(() => {
    function recompute() {
      if (paused) return
      const now = Date.now()
      setElapsed(Math.floor((now - startTimeRef.current - pausedAccumRef.current) / 1000))
    }
    recompute()
    intervalRef.current = setInterval(recompute, 1000)
    return () => clearInterval(intervalRef.current)
  }, [paused])

  // 倒计时归零自动完成
  useEffect(() => {
    if (isCountdown && remaining <= 0) {
      onComplete(task.id)
    }
  }, [remaining, isCountdown])

  // 切回 tab 时立即补齐显示（interval 可能被节流到 1 次/分钟，不等下一个 tick）
  useEffect(() => {
    function handleVisibility() {
      if (document.hidden || paused) return
      const now = Date.now()
      setElapsed(Math.floor((now - startTimeRef.current - pausedAccumRef.current) / 1000))
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [paused])

  const displaySeconds = isCountdown ? remaining : elapsed
  const mm = String(Math.floor(displaySeconds / 60)).padStart(2, '0')
  const ss = String(displaySeconds % 60).padStart(2, '0')

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 200,
      background: 'var(--color-base)',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      padding: 40,
    }}>
      {/* 针叶暗纹背景层（复用 design tokens） */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        opacity: 0.06,
        backgroundRepeat: 'repeat',
        backgroundSize: '360px 240px',
        backgroundImage: `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='360' height='240' viewBox='0 0 360 240'><g fill='%234896c4' opacity='0.45'><path d='M40 200 L30 160 L50 160 Z M35 170 L25 130 L45 130 Z M37 140 L28 100 L46 100 Z'/><path d='M140 210 L128 170 L152 170 Z M134 180 L124 140 L144 140 Z'/><path d='M260 200 L248 160 L272 160 Z M254 170 L244 130 L264 130 Z M256 140 L247 100 L265 100 Z M258 110 L250 80 L266 80 Z'/><path d='M340 205 L330 170 L350 170 Z M335 180 L325 145 L345 145 Z'/></g></svg>")`,
      }} />

      {/* 计时器 */}
      <div style={{
        fontSize: 96,
        fontWeight: 300,
        fontVariantNumeric: 'tabular-nums',
        letterSpacing: '-0.02em',
        color: 'var(--color-text)',
        lineHeight: 1,
        marginBottom: 16,
        fontFeatureSettings: '"ss01"',
      }}>
        {mm}:{ss}
      </div>

      {/* 任务标签 */}
      <div style={{
        fontSize: 15,
        color: 'var(--color-subtle)',
        marginBottom: tooShortHint ? 12 : 48,
      }}>
        {isCountdown ? 'focus' : 'open'} · {task.keyword}
      </div>

      {tooShortHint && (
        <div style={{
          fontSize: 13, color: 'var(--color-primary)',
          marginBottom: 24,
          transition: 'opacity 0.3s ease',
        }}>
          不到一分钟哦，再坚持一下？
        </div>
      )}

      {/* 控制按钮 */}
      <div style={{ display: 'flex', gap: 16 }}>
        <button
          onClick={() => setPaused(!paused)}
          style={{
            padding: '12px 28px', borderRadius: 'var(--radius)',
            border: '1px solid var(--color-line)',
            background: 'var(--color-surface)',
            color: 'var(--color-text)',
            fontSize: 15, fontFamily: 'inherit', cursor: 'pointer',
          }}
        >
          {paused ? '继续' : '暂停'}
        </button>
        <button
          onClick={() => {
            if (elapsed < 60) {
              setTooShortHint(true)
              setTimeout(() => setTooShortHint(false), 2500)
              return
            }
            onComplete(task.id)
          }}
          style={{
            padding: '12px 28px', borderRadius: 'var(--radius)',
            border: '1px solid var(--color-primary)',
            background: 'var(--color-primary)',
            color: '#fff',
            fontSize: 15, fontFamily: 'inherit', cursor: 'pointer',
          }}
        >
          完成
        </button>
        <button
          onClick={() => onAbandon(task.id)}
          style={{
            padding: '12px 28px', borderRadius: 'var(--radius)',
            border: '1px solid var(--color-line)',
            background: 'transparent',
            color: 'var(--color-subtle)',
            fontSize: 15, fontFamily: 'inherit', cursor: 'pointer',
          }}
        >
          放弃
        </button>
      </div>

      {/* 桌宠占位（第 3 步做真 SVG 白鼬） */}
      <div style={{
        position: 'absolute', bottom: 40, right: 40,
        width: 60, height: 60, borderRadius: '50%',
        background: 'var(--color-accent-soft)',
        border: '1px solid var(--color-accent)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 24,
      }}>
        ❄
      </div>
    </div>
  )
}

function parseTaskTime(value) {
  if (!value) return null
  const ms = Date.parse(value)
  return Number.isNaN(ms) ? null : ms
}
