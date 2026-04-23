/**
 * 白鼬 SVG 组件——按 state 切不同姿态。
 *
 * Props:
 *   view: "full" | "half"  默认 "full"
 *     - full：全身展示
 *     - half：只露上半身（靠 overflow:hidden 裁底）
 *   state: "idle" | "listening" | "thinking"
 *     - idle      → stoat-front     正脸默认
 *     - listening → stoat-side      侧脸（用户在打字）
 *     - thinking  → stoat-side + 头顶 3 点泡泡
 *   width: 数字，默认 220
 *
 * 所有姿态 SVG 比例统一约 1640:2554 ≈ 0.642（Sephy 出图时已对齐头身比）
 */

import frontSrc from '../assets/stoat-front.svg'
import sideSrc from '../assets/stoat-side.svg'

const SVG_BY_STATE = {
  idle:      frontSrc,
  listening: frontSrc,   // 用户打字时仍用正脸（侧脸太"沉思"，正脸是"在看你"）
  thinking:  sideSrc,    // 侧脸 + 泡泡 overlay
}

const SVG_RATIO = 1640 / 2554   // ≈ 0.642

export default function StoatHalf({ view = 'full', state = 'idle', width = 220 }) {
  const src = SVG_BY_STATE[state] || frontSrc
  const fullHeight = width / SVG_RATIO
  const containerHeight = view === 'half' ? fullHeight * 0.5 : fullHeight

  // listening 不做摇晃；thinking 用紧一点的呼吸
  const animation =
    state === 'thinking'  ? 'stoat-breath 1.6s ease-in-out infinite' :
                            'stoat-breath 4s ease-in-out infinite'

  return (
    <div style={{ width, position: 'relative', display: 'inline-block', lineHeight: 0 }}>
      {/* thinking 时头顶 3 点泡泡 */}
      {state === 'thinking' && <ThinkingDots />}

      <div style={{
        width,
        height: containerHeight,
        overflow: 'hidden',
      }}>
        <style>{`
          @keyframes stoat-breath {
            0%,100% { transform: scale(1); }
            50%     { transform: scale(1.015); }
          }
        `}</style>
        <img
          src={src}
          alt="小白"
          style={{
            width: '100%',
            height: 'auto',
            display: 'block',
            animation,
            transformOrigin: '50% 100%',
            transition: 'opacity 200ms ease-out',
          }}
        />
      </div>
    </div>
  )
}

function ThinkingDots() {
  return (
    <div style={{
      position: 'absolute',
      top: 4,
      left: '50%',
      transform: 'translateX(30%)',
      background: 'white',
      border: `1.5px solid var(--color-text)`,
      borderRadius: 14,
      padding: '4px 10px',
      display: 'flex',
      gap: 3,
      lineHeight: 0,
      zIndex: 2,
    }}>
      <style>{`
        @keyframes stoat-think-dot {
          0%, 80%, 100% { opacity: 0.3; }
          40%           { opacity: 1; }
        }
        .think-dot { animation: stoat-think-dot 1.4s ease-in-out infinite; }
        .think-dot:nth-child(2) { animation-delay: 0.2s; }
        .think-dot:nth-child(3) { animation-delay: 0.4s; }
      `}</style>
      <span className="think-dot" style={{ width: 4, height: 4, borderRadius: '50%', background: 'var(--color-text)', display: 'inline-block' }} />
      <span className="think-dot" style={{ width: 4, height: 4, borderRadius: '50%', background: 'var(--color-text)', display: 'inline-block' }} />
      <span className="think-dot" style={{ width: 4, height: 4, borderRadius: '50%', background: 'var(--color-text)', display: 'inline-block' }} />
    </div>
  )
}
