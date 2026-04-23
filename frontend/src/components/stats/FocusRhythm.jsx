/**
 * 03 · 我的专注时段 · 两个子图
 *   上：一天里什么时候（24h 分布）
 *   下：这个月每一天（30 天每日趋势）
 */

import { useRef, useEffect } from 'react'
import SectionHead from './SectionHead.jsx'

const pad2 = n => String(n).padStart(2, '0')

function Bars({ data, showLabelFn, tooltipFn, initialScrollPercent = 0, wideLabel = false }) {
  const scrollRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current && initialScrollPercent > 0) {
      const el = scrollRef.current
      requestAnimationFrame(() => {
        el.scrollLeft = el.scrollWidth * initialScrollPercent
      })
    }
  }, [initialScrollPercent])

  const maxVal = Math.max(...data.map(d => d.value), 1)
  const maxH = 150

  return (
    <div
      ref={scrollRef}
      className="stats-bars-scroll"
      style={{
        overflowX: 'auto',
        overflowY: 'visible',
        padding: '10px 0 18px',
        scrollbarWidth: 'thin',
      }}
    >
      <div style={{
        display: 'flex',
        alignItems: 'flex-end',
        gap: wideLabel ? 14 : 8,
        height: 180,
        padding: '0 8px',
        minWidth: 'max-content',
      }}>
        {data.map((d, i) => {
          const h = d.value === 0 ? 3 : Math.max(8, (d.value / maxVal) * maxH)
          const isPeak = d.peak
          const isEmpty = d.value === 0 && !d.future
          const showLabel = showLabelFn(d, i) || isPeak

          return (
            <div
              key={i}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 10,
                minWidth: wideLabel ? 36 : 24,
              }}
            >
              <div
                className="stats-bar"
                style={{
                  width: 18,
                  height: d.future ? 3 : h,
                  background: d.future
                    ? 'var(--color-line-soft)'
                    : isPeak
                      ? 'var(--color-primary)'
                      : (isEmpty ? 'var(--color-line)' : 'var(--color-accent)'),
                  borderRadius: '3px 3px 1px 1px',
                  position: 'relative',
                  animationDelay: (i * 20) + 'ms',
                }}
              >
                <div className="stats-bar-tooltip">{tooltipFn(d)}</div>
              </div>
              <div
                className="stats-tabular"
                style={{
                  fontFamily: "'IBM Plex Serif', serif",
                  fontSize: 10,
                  color: isPeak ? 'hsl(202, 55%, 38%)' : 'var(--color-muted)',
                  letterSpacing: '0.04em',
                  fontWeight: isPeak ? 500 : 400,
                  visibility: showLabel ? 'visible' : 'hidden',
                  whiteSpace: 'nowrap',
                }}
              >{d.label}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function SubHead({ title, meta }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'baseline',
      padding: '0 4px',
      marginBottom: 12,
    }}>
      <span style={{
        fontSize: 13,
        color: 'var(--color-text)',
        letterSpacing: '0.04em',
      }}>
        <span style={{
          color: 'var(--color-primary)',
          fontWeight: 500,
          marginRight: 8,
        }}>·</span>
        {title}
      </span>
      <span style={{
        fontSize: 11,
        color: 'var(--color-subtle)',
      }}>{meta}</span>
    </div>
  )
}

function Hl({ children }) {
  return (
    <span
      className="stats-tabular"
      style={{
        fontFamily: "'IBM Plex Serif', serif",
        color: 'hsl(202, 55%, 38%)',
        fontWeight: 500,
        margin: '0 2px',
      }}
    >{children}</span>
  )
}

export default function FocusRhythm({ hours24, days30, todayDate }) {
  // 24h
  const h24 = hours24 || []
  const peakHour = h24.reduce(
    (p, c) => (c.minutes > (p?.minutes || 0) ? c : p),
    null,
  )
  const peakHourText = peakHour && peakHour.minutes > 0
    ? `${pad2(peakHour.hour)}:00-${pad2((peakHour.hour + 1) % 24)}:00`
    : '尚无'

  const hoursData = h24.map(h => ({
    value: h.minutes,
    peak: peakHour && peakHour.minutes > 0 && h.hour === peakHour.hour,
    label: h.hour + '点',
    hour: h.hour,
  }))

  // 30d
  const d30 = days30 || []
  const todayMinutes = d30.find(d => d.date === todayDate)?.minutes || 0

  const daysData = d30.map(d => {
    const isToday = d.date === todayDate
    const isFuture = todayDate ? d.date > todayDate : false
    const parts = d.date.split('-')
    const m = parseInt(parts[1], 10)
    const day = parseInt(parts[2], 10)
    return {
      value: d.minutes,
      peak: isToday,
      future: isFuture,
      date: d.date,
      monthDay: parts[1] + '/' + parts[2],
      label: `${m}-${day}`,
    }
  })

  return (
    <section className="stats-card" style={{
      background: 'var(--color-surface)',
      border: '1.5px solid var(--color-line)',
      borderRadius: 'var(--radius)',
      padding: '32px 32px 30px',
    }}>
      <SectionHead num="03" label="我的专注时段" />

      {/* 一天里什么时候 */}
      <SubHead title="每日专注" meta={<span>高峰在 <Hl>{peakHourText}</Hl></span>} />
      <Bars
        data={hoursData}
        showLabelFn={(d) => d.value > 0}
        tooltipFn={(d) => {
          const t = pad2(d.hour) + ':00'
          return d.value === 0 ? (t + ' · 无') : (t + ' · ' + d.value + ' min')
        }}
        initialScrollPercent={0.25}
      />

      <div style={{
        height: 1,
        background: 'var(--color-line-soft)',
        margin: '18px 0 22px',
      }}></div>

      {/* 这个月每一天 */}
      <SubHead title="每月专注" meta={<span>今日 <Hl>{todayMinutes} min</Hl></span>} />
      <Bars
        data={daysData}
        showLabelFn={() => true}
        tooltipFn={(d) => {
          if (d.future) return d.monthDay + ' · 还没到'
          return d.value === 0 ? (d.monthDay + ' · 休息') : (d.monthDay + ' · ' + d.value + ' min')
        }}
        initialScrollPercent={1.0}
        wideLabel={true}
      />
    </section>
  )
}
