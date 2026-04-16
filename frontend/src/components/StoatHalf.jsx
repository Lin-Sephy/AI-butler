/**
 * 白鼬 SVG 组件——直接用 Sephy 给的 stoat-standing.svg。
 *
 * Props:
 *   view: "full" | "half"  默认 "half"
 *     - full：全身展示（闲玩 mode 居中）
 *     - half：只露上半身（聊天 mode 趴在聊天框上沿），靠 overflow:hidden 裁
 *   state: "idle" | "listening" | "thinking"
 *   width: 数字，默认 120
 */

import stoatSrc from '../assets/stoat-standing.svg'

export default function StoatHalf({ view = 'half', state = 'idle', width = 120 }) {
  // SVG 原图比例 1103:1461 ≈ 0.755。half 视图只露上 50%，容器高度按比例算
  const fullHeight = width / 0.755
  const containerHeight = view === 'half' ? fullHeight * 0.5 : fullHeight

  const animation =
    state === 'listening' ? 'stoat-tilt 2.4s ease-in-out infinite' :
    state === 'thinking'  ? 'stoat-breath 1.6s ease-in-out infinite' :   // 紧张点的呼吸
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
          @keyframes stoat-tilt {
            0%,100% { transform: rotate(-1.5deg); }
            50%     { transform: rotate(1.5deg); }
          }
        `}</style>
        <img
          src={stoatSrc}
          alt="小白"
          style={{
            width: '100%',
            height: 'auto',
            display: 'block',
            animation,
            transformOrigin: view === 'half' ? '50% 100%' : '50% 100%',
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
      top: -10,
      left: '50%',
      transform: 'translateX(40%)',
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
