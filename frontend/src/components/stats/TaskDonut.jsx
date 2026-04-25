/**
 * 02 · 任务分布 · 环形图居中 + 引线 callout 标注任务时长
 * 带日/周/月切换，前端从 distribution.day/week/month 三块里按 tab 取
 */

import { useState } from 'react'
import SectionHead from './SectionHead.jsx'

// 段颜色（按 pct 从大到小应用）
const SEG_COLORS = [
  'hsl(202, 55%, 42%)',
  'hsl(202, 45%, 58%)',
  'hsl(198, 45%, 72%)',
  'hsl(198, 45%, 82%)',
  'hsl(220, 15%, 85%)',
]

const RANGES = [
  { key: 'day',   label: '日' },
  { key: 'week',  label: '周' },
  { key: 'month', label: '月' },
]

// 环形图几何参数（SVG viewBox 0 0 240 160）
const CX = 120
const CY = 80
const R = 38
// 环 stroke-width 18，所以环的"体"位于 R-9=29 到 R+9=47。
// dot 放在 R=43——略探入环内缘一点，视觉上"钉"在环上而不是浮在环外
const R_DOT = 43
const R_TURN = 56        // 转折点半径（引线向外转折）
const LABEL_X_LEFT = 50
const LABEL_X_RIGHT = 190

function formatMin(m) {
  if (!m || m < 60) return (m || 0) + 'min'
  const h = Math.floor(m / 60)
  const mm = m % 60
  return mm === 0 ? h + 'h' : h + 'h ' + mm + 'min'
}

// 超过 5 段合并成"其他"
function compact(items) {
  if (!items?.length) return []
  if (items.length <= 5) return items.slice()
  const top4 = items.slice(0, 4)
  const restMin = items.slice(4).reduce((s, it) => s + it.minutes, 0)
  const restPct = items.slice(4).reduce((s, it) => s + it.pct, 0)
  return [...top4, { keyword: '其他', minutes: restMin, pct: Math.round(restPct * 10) / 10 }]
}

// 算每段的 dasharray/offset + 引线布局
function layout(items) {
  const circumference = 2 * Math.PI * R
  let cumPct = 0

  const segs = items.map((it, i) => {
    const segLen = (it.pct / 100) * circumference
    const offset = -(cumPct / 100) * circumference
    const midPct = cumPct + it.pct / 2
    cumPct += it.pct

    const angleDeg = (midPct / 100) * 360
    const angleRad = angleDeg * Math.PI / 180
    const sin = Math.sin(angleRad)
    const cos = Math.cos(angleRad)

    const x0 = CX + R_DOT * sin
    const y0 = CY - R_DOT * cos
    const xTurn = CX + R_TURN * sin
    const yTurn = y0   // 将被重叠检测修正
    const isRight = angleDeg < 180
    const xLabel = isRight ? LABEL_X_RIGHT : LABEL_X_LEFT

    return {
      ...it,
      color: SEG_COLORS[i] || SEG_COLORS[SEG_COLORS.length - 1],
      dash: `${segLen} ${circumference}`,
      offset,
      x0, y0, xTurn, yTurn,
      xLabel,
      isRight,
      _origYTurn: y0,
    }
  })

  // 按左右分组后做简单防重叠：相邻 label 最小间距 14
  const MIN_GAP = 18
  const adjust = (group) => {
    group.sort((a, b) => a.yTurn - b.yTurn)
    for (let i = 1; i < group.length; i++) {
      const gap = group[i].yTurn - group[i - 1].yTurn
      if (gap < MIN_GAP) group[i].yTurn = group[i - 1].yTurn + MIN_GAP
    }
  }
  adjust(segs.filter(s => s.isRight))
  adjust(segs.filter(s => !s.isRight))

  return segs
}

export default function TaskDonut({ distribution }) {
  const [range, setRange] = useState('day')
  const bucket = distribution?.[range] || { total_minutes: 0, items: [] }
  const items = compact(bucket.items)
  const segments = layout(items)
  const totalText = formatMin(bucket.total_minutes)

  return (
    <section className="stats-card" style={{
      background: 'var(--color-surface)',
      border: '1.5px solid var(--color-line)',
      borderRadius: 'var(--radius)',
      padding: '32px 32px 30px',
    }}>
      <SectionHead
        num="02"
        label="任务分布"
        extra={
          <div style={{
            display: 'inline-flex',
            background: 'var(--color-accent-soft)',
            borderRadius: 99,
            padding: 3,
            gap: 2,
          }}>
            {RANGES.map(r => {
              const active = range === r.key
              return (
                <button
                  key={r.key}
                  className="stats-tab"
                  onClick={() => setRange(r.key)}
                  style={{
                    fontFamily: 'inherit',
                    fontSize: 12,
                    color: active ? 'var(--color-text)' : 'var(--color-subtle)',
                    padding: '6px 14px',
                    borderRadius: 99,
                    border: 'none',
                    background: active ? 'var(--color-surface)' : 'transparent',
                    boxShadow: active ? '0 0 0 1px var(--color-accent)' : 'none',
                    cursor: 'pointer',
                    fontWeight: 400,
                    transition: 'all 350ms ease',
                  }}
                >{r.label}</button>
              )
            })}
          </div>
        }
      />

      {segments.length === 0 ? (
        <div style={{
          textAlign: 'center',
          padding: '40px 20px',
          color: 'var(--color-muted)',
          fontSize: 13,
        }}>
          这段时间还没有专注记录
        </div>
      ) : (
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          padding: '10px 0 6px',
        }}>
          <svg viewBox="0 0 240 160" overflow="visible" style={{ width: '100%', maxWidth: 520, height: 'auto', display: 'block' }}>
            {/* 环 */}
            <g transform={`rotate(-90 ${CX} ${CY})`}>
              <circle cx={CX} cy={CY} r={R} fill="none" stroke="var(--color-line-soft)" strokeWidth="18" />
              {segments.map((s, i) => (
                <circle
                  key={i}
                  cx={CX} cy={CY} r={R}
                  fill="none"
                  stroke={s.color}
                  strokeWidth="18"
                  strokeLinecap="butt"
                  strokeDasharray={s.dash}
                  strokeDashoffset={s.offset}
                />
              ))}
            </g>

            {/* 中心总时长 */}
            <text
              x={CX} y={CY + 3}
              textAnchor="middle"
              style={{
                fontFamily: "'IBM Plex Serif', serif",
                fontSize: 10,
                fontWeight: 400,
                fill: 'var(--color-text)',
                fontVariantNumeric: 'tabular-nums',
              }}
            >{totalText}</text>

            {/* 引线 + label */}
            {segments.map((s, i) => (
              <g key={i}>
                <polyline
                  points={`${s.x0.toFixed(1)},${s._origYTurn.toFixed(1)} ${s.xTurn.toFixed(1)},${s.yTurn.toFixed(1)} ${(s.isRight ? LABEL_X_RIGHT - 1 : LABEL_X_LEFT + 1).toFixed(1)},${s.yTurn.toFixed(1)}`}
                  fill="none"
                  stroke="hsl(240, 3%, 70%)"
                  strokeWidth="0.6"
                />
                <circle cx={s.x0} cy={s._origYTurn} r="1" fill="var(--color-text)" />
                <text
                  x={s.xLabel}
                  y={s.yTurn - 2}
                  textAnchor={s.isRight ? 'start' : 'end'}
                  style={{
                    fontFamily: "'Noto Serif SC', serif",
                    fontSize: 8,
                    fill: 'var(--color-text)',
                    fontWeight: 400,
                  }}
                >{s.keyword}</text>
                <text
                  x={s.xLabel}
                  y={s.yTurn + 7}
                  textAnchor={s.isRight ? 'start' : 'end'}
                  style={{
                    fontFamily: "'IBM Plex Serif', serif",
                    fontSize: 7,
                    fill: 'var(--color-subtle)',
                    fontVariantNumeric: 'tabular-nums',
                    letterSpacing: '0.02em',
                  }}
                >{formatMin(s.minutes)}</text>
              </g>
            ))}
          </svg>
        </div>
      )}
    </section>
  )
}
