/**
 * 04 · 累计 · 松林打卡
 * 累计天数 → 松树棵数映射：
 *   1-3 天: 2 棵 / 4-7: 4 / 8-14: 6 / 15-30: 8 / 30+: 10
 * SVG 用 feTurbulence filter 把三角形边做成针叶质感
 * 三层空间雾化（前景清晰 / 中景微扰 / 远景 blur）
 */

import SectionHead from './SectionHead.jsx'

function getVisibleTrees(days) {
  // 每一天专注对应种一棵树（和 caption 文案一致），最多 10 棵
  return Math.min(Math.max(days || 0, 0), 10)
}

function getFogOpacity(days) {
  // 远景雾气随累计天数散开，两阶段叙事：
  //   1-10 天：前景+中景依次种出 10 棵，远景保持 0.55 初始雾气
  //   11-30 天：远景 opacity 从 0.55 线性升到 1.0，雾慢慢散开林子"变深"
  //   30+ 天：远景 1.0 稳态，不再变化（不鼓励越用越多的上瘾型打卡）
  const d = days || 0
  if (d <= 10) return 0.55
  if (d >= 30) return 1.0
  return 0.55 + (d - 10) * (1.0 - 0.55) / 20
}

export default function PineGrove({ days, minutes }) {
  const total = days || 0
  const hours = Math.floor((minutes || 0) / 60)
  const visible = getVisibleTrees(total)
  const visibleAt = n => visible >= n
  const fogOpacity = getFogOpacity(total)

  return (
    <section className="stats-card stats-grove-card" style={{
      background: 'var(--color-surface)',
      border: '1.5px solid var(--color-line)',
      borderRadius: 'var(--radius)',
      padding: '32px 32px 0',
      overflow: 'hidden',
    }}>
      <SectionHead num="04" label="累计" />

      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        padding: '0 4px 10px',
        flexWrap: 'wrap',
        gap: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 16 }}>
          <div
            className="stats-grove-days stats-tabular"
            style={{
              fontFamily: "'IBM Plex Serif', serif",
              fontSize: 56,
              fontWeight: 300,
              color: 'var(--color-text)',
              letterSpacing: '-0.02em',
              lineHeight: 1,
            }}
          >
            {total}<span style={{
              fontSize: 18,
              color: 'var(--color-subtle)',
              fontWeight: 400,
            }}> 天</span>
          </div>
          <div style={{
            fontSize: 13,
            color: 'var(--color-muted)',
            letterSpacing: '0.04em',
            paddingBottom: 4,
          }}>
            已陪伴你 <span style={{
              fontFamily: "'IBM Plex Serif', serif",
              color: 'var(--color-subtle)',
              fontVariantNumeric: 'tabular-nums',
              margin: '0 2px',
            }}>{hours}</span> 小时
          </div>
        </div>
        <div style={{
          fontSize: 11,
          color: 'var(--color-muted)',
          letterSpacing: '0.08em',
          textAlign: 'right',
          maxWidth: 220,
        }}>每一天的专注，都让林子长出一棵</div>
      </div>

      <div className="stats-grove-svg-wrap" style={{
        margin: '0 -32px',
        position: 'relative',
      }}>
        <svg
          viewBox="0 0 760 170"
          preserveAspectRatio="xMidYMax slice"
          style={{ display: 'block', width: '100%', height: 170 }}
          aria-label="松林"
        >
          <defs>
            <filter id="pg-needle-front" x="-5%" y="-5%" width="110%" height="110%">
              <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="3" />
              <feDisplacementMap in="SourceGraphic" scale="2.5" />
            </filter>
            <filter id="pg-needle-mid" x="-5%" y="-5%" width="110%" height="110%">
              <feTurbulence type="fractalNoise" baseFrequency="1.1" numOctaves="2" seed="7" />
              <feDisplacementMap in="SourceGraphic" scale="1.8" />
            </filter>
            <filter id="pg-needle-back" x="-5%" y="-5%" width="110%" height="110%">
              <feGaussianBlur stdDeviation="1.2" />
            </filter>

            <linearGradient id="pg-snow" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="hsl(222, 57%, 98%)" />
              <stop offset="100%" stopColor="hsl(222, 57%, 94%)" />
            </linearGradient>
            <linearGradient id="pg-mist" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="hsl(222, 40%, 92%)" stopOpacity="0.4" />
              <stop offset="100%" stopColor="hsl(222, 40%, 96%)" stopOpacity="0" />
            </linearGradient>

            <symbol id="pg-pine" viewBox="0 0 40 120">
              <path d="M 20 5 L 28 30 L 12 30 Z" fill="currentColor" />
              <path d="M 20 25 L 30 50 L 10 50 Z" fill="currentColor" />
              <path d="M 20 45 L 33 72 L 7 72 Z" fill="currentColor" />
              <path d="M 20 65 L 36 95 L 4 95 Z" fill="currentColor" />
              <rect x="17.5" y="92" width="5" height="14" fill="#7a6957" />
            </symbol>
            <symbol id="pg-pine-mid" viewBox="0 0 40 120">
              <path d="M 20 10 L 27 35 L 13 35 Z" fill="currentColor" />
              <path d="M 20 30 L 30 58 L 10 58 Z" fill="currentColor" />
              <path d="M 20 52 L 34 85 L 6 85 Z" fill="currentColor" />
              <rect x="17.5" y="82" width="5" height="12" fill="#7a6957" />
            </symbol>
            <symbol id="pg-pine-far" viewBox="0 0 40 120">
              <path d="M 20 20 L 26 45 L 14 45 Z" fill="currentColor" />
              <path d="M 20 40 L 30 72 L 10 72 Z" fill="currentColor" />
              <rect x="18" y="70" width="4" height="10" fill="#7a6957" />
            </symbol>
            <symbol id="pg-pine-placeholder" viewBox="0 0 40 120">
              <path d="M 20 25 L 30 58 L 10 58 Z"
                    fill="none" stroke="hsl(240, 3%, 82%)" strokeWidth="1" strokeDasharray="2 3" />
              <path d="M 20 50 L 34 85 L 6 85 Z"
                    fill="none" stroke="hsl(240, 3%, 82%)" strokeWidth="1" strokeDasharray="2 3" />
            </symbol>
          </defs>

          {/* 雾感天空 */}
          <rect x="0" y="0" width="760" height="140" fill="url(#pg-mist)" />

          {/* 远景：opacity 随累计天数从 0.55 线性升到 1.0（11-30 天阶段叙事）*/}
          <g filter="url(#pg-needle-back)" opacity={fogOpacity}>
            <use href="#pg-pine-far" x="40"  y="56" width="40" height="120" color="hsl(202, 35%, 70%)" />
            <use href="#pg-pine-far" x="90"  y="48" width="40" height="120" color="hsl(202, 35%, 68%)" />
            <use href="#pg-pine-far" x="170" y="52" width="40" height="120" color="hsl(202, 35%, 72%)" />
            <use href="#pg-pine-far" x="250" y="50" width="40" height="120" color="hsl(202, 35%, 70%)" />
            <use href="#pg-pine-far" x="340" y="54" width="40" height="120" color="hsl(202, 35%, 72%)" />
            <use href="#pg-pine-far" x="440" y="48" width="40" height="120" color="hsl(202, 35%, 68%)" />
            <use href="#pg-pine-far" x="540" y="52" width="40" height="120" color="hsl(202, 35%, 70%)" />
            <use href="#pg-pine-far" x="620" y="50" width="40" height="120" color="hsl(202, 35%, 72%)" />
            <use href="#pg-pine-far" x="700" y="54" width="40" height="120" color="hsl(202, 35%, 70%)" />
          </g>

          {/* 中景 · tree 7-10 */}
          <g filter="url(#pg-needle-mid)">
            {visibleAt(7) && (
              <g className="stats-tree" style={{ '--tree-opacity': 0.78, animationDelay: '300ms' }}>
                <use href="#pg-pine-mid" x="70" y="30" width="44" height="120" color="#4896c4" />
              </g>
            )}
            {visibleAt(8) && (
              <g className="stats-tree" style={{ '--tree-opacity': 0.72, animationDelay: '380ms' }}>
                <use href="#pg-pine-mid" x="220" y="22" width="48" height="132" color="#4896c4" />
              </g>
            )}
            {visibleAt(9) && (
              <g className="stats-tree" style={{ '--tree-opacity': 0.75, animationDelay: '460ms' }}>
                <use href="#pg-pine-mid" x="380" y="28" width="44" height="124" color="#4896c4" />
              </g>
            )}
            {visibleAt(10) && (
              <g className="stats-tree" style={{ '--tree-opacity': 0.72, animationDelay: '540ms' }}>
                <use href="#pg-pine-mid" x="500" y="22" width="48" height="130" color="#4896c4" />
              </g>
            )}
          </g>

          {/* 前景 · tree 1-6 */}
          <g filter="url(#pg-needle-front)">
            {visibleAt(1) && (
              <g className="stats-tree" style={{ '--tree-opacity': 1, animationDelay: '80ms' }}>
                <use href="#pg-pine" x="30" y="18" width="52" height="138" color="#3d7ca3" />
              </g>
            )}
            {visibleAt(2) && (
              <g className="stats-tree" style={{ '--tree-opacity': 1, animationDelay: '140ms' }}>
                <use href="#pg-pine" x="150" y="8" width="56" height="150" color="#4896c4" />
              </g>
            )}
            {visibleAt(3) && (
              <g className="stats-tree" style={{ '--tree-opacity': 1, animationDelay: '200ms' }}>
                <use href="#pg-pine" x="300" y="12" width="52" height="144" color="#3d7ca3" />
              </g>
            )}
            {visibleAt(4) && (
              <g className="stats-tree" style={{ '--tree-opacity': 1, animationDelay: '260ms' }}>
                <use href="#pg-pine" x="450" y="6" width="58" height="152" color="#4896c4" />
              </g>
            )}
            {visibleAt(5) && (
              <g className="stats-tree" style={{ '--tree-opacity': 0.92, animationDelay: '600ms' }}>
                <use href="#pg-pine" x="600" y="14" width="54" height="144" color="#4896c4" />
              </g>
            )}
            {visibleAt(6) && (
              <g className="stats-tree" style={{ '--tree-opacity': 0.92, animationDelay: '660ms' }}>
                <use href="#pg-pine" x="700" y="18" width="50" height="138" color="#3d7ca3" />
              </g>
            )}
          </g>

          {/* 永久占位虚线（"还能再种"暗示）*/}
          <g opacity="0.65">
            <use href="#pg-pine-placeholder" x="106" y="50" width="38" height="110" />
            <use href="#pg-pine-placeholder" x="276" y="50" width="36" height="108" />
            <use href="#pg-pine-placeholder" x="410" y="50" width="38" height="110" />
            <use href="#pg-pine-placeholder" x="560" y="50" width="36" height="108" />
          </g>

          {/* 雪地（贝塞尔起伏）*/}
          <path d="M 0 140 C 70 132, 140 148, 210 138 C 280 130, 340 146, 410 138 C 480 132, 540 150, 620 140 C 680 134, 720 146, 760 140 L 760 170 L 0 170 Z"
                fill="url(#pg-snow)" />
          <path d="M 0 140 C 70 132, 140 148, 210 138 C 280 130, 340 146, 410 138 C 480 132, 540 150, 620 140 C 680 134, 720 146, 760 140"
                fill="none" stroke="hsl(222, 57%, 99%)" strokeWidth="1.5" opacity="0.8" />

          {/* 雪堆 */}
          <g opacity="0.8" fill="hsl(222, 57%, 98%)">
            <ellipse cx="80" cy="148" rx="14" ry="3" />
            <ellipse cx="250" cy="150" rx="18" ry="3.5" />
            <ellipse cx="480" cy="149" rx="16" ry="3" />
            <ellipse cx="680" cy="151" rx="15" ry="3" />
          </g>

          {/* 飘雪粒 */}
          <g fill="#4896c4" opacity="0.25">
            <circle cx="120" cy="30" r="1" />
            <circle cx="340" cy="45" r="0.8" />
            <circle cx="580" cy="25" r="1" />
            <circle cx="720" cy="42" r="0.8" />
          </g>
        </svg>
      </div>
    </section>
  )
}
