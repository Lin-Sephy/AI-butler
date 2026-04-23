/**
 * 数据页 · 你的专注印记
 * 四个 section：今日 HERO / 任务分布环形图 / 专注时段（24h + 30d）/ 累计松林
 *
 * 数据从 /api/stats/dashboard 一次性取回（不调 DS，纯 Python 聚合）。
 * 设计稿 ground truth：docs/references/白鼬/数据页设计稿-v2.html
 */

import { useEffect, useState } from 'react'
import { apiFetch } from '../lib/api.js'
import HeroToday from '../components/stats/HeroToday.jsx'
import TaskDonut from '../components/stats/TaskDonut.jsx'
import FocusRhythm from '../components/stats/FocusRhythm.jsx'
import PineGrove from '../components/stats/PineGrove.jsx'
import './StatsPage.css'

export default function StatsPage() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    apiFetch('/api/stats/dashboard')
      .then(d => {
        if (!cancelled) { setData(d); setLoading(false) }
      })
      .catch(e => {
        if (!cancelled) { setError(e); setLoading(false) }
      })
    return () => { cancelled = true }
  }, [])

  if (loading) {
    return (
      <div style={{
        padding: '60px 20px',
        textAlign: 'center',
        color: 'var(--color-subtle)',
        fontSize: 14,
      }}>正在整理数据...</div>
    )
  }

  if (error) {
    return (
      <div style={{
        background: 'hsl(0, 60%, 97%)',
        border: '1px solid hsl(0, 50%, 88%)',
        borderRadius: 'var(--radius)',
        padding: 20,
        color: 'hsl(0, 40%, 35%)',
        fontSize: 13,
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        flexWrap: 'wrap',
      }}>
        <span>数据加载失败：{error.message || '网络问题'}</span>
        <button
          onClick={() => window.location.reload()}
          style={{
            background: 'transparent',
            border: '1px solid hsl(0, 40%, 35%)',
            color: 'hsl(0, 40%, 35%)',
            padding: '4px 12px',
            borderRadius: 99,
            fontSize: 12,
            cursor: 'pointer',
            fontFamily: 'inherit',
          }}
        >重试</button>
      </div>
    )
  }

  const dateStr = (data?.today_date || '').replaceAll('-', ' · ')

  return (
    <div style={{
      position: 'relative',
    }}>
      <div className="stats-snow" aria-hidden="true">
        <span></span><span></span><span></span><span></span><span></span>
      </div>

      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 28,
        position: 'relative',
        zIndex: 1,
      }}>
        <div style={{
          padding: '8px 8px 4px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          flexWrap: 'wrap',
          gap: 12,
        }}>
          <h1 className="stats-page-title" style={{
            fontSize: 30,
            fontWeight: 400,
            letterSpacing: '0.01em',
            color: 'var(--color-text)',
            margin: 0,
          }}>你的专注印记</h1>
          <div
            className="stats-tabular"
            style={{
              fontFamily: "'IBM Plex Serif', serif",
              fontSize: 12,
              color: 'var(--color-muted)',
              letterSpacing: '0.06em',
            }}
          >{dateStr}</div>
        </div>

        <HeroToday data={data?.today} />
        <TaskDonut distribution={data?.distribution} />
        <FocusRhythm
          hours24={data?.hours_24}
          days30={data?.days_30}
          todayDate={data?.today_date}
        />
        <PineGrove
          days={data?.cumulative?.total_days}
          minutes={data?.cumulative?.total_minutes}
        />
      </div>
    </div>
  )
}
