/**
 * 01 · 今日 · HERO
 * 大字今日总专注时长 + 右侧任务数 + 最常做的事胶囊
 */

import SectionHead from './SectionHead.jsx'

const UNIT_SM = {
  fontSize: 22,
  color: 'var(--color-subtle)',
  fontWeight: 400,
  letterSpacing: '0.02em',
  marginLeft: 2,
}

const ITEM_LABEL = {
  fontSize: 11,
  color: 'var(--color-muted)',
  marginBottom: 6,
  letterSpacing: '0.06em',
}

export default function HeroToday({ data }) {
  const total = data?.total_minutes || 0
  const hours = Math.floor(total / 60)
  const mins = total % 60
  const tasks = data?.tasks_completed || 0
  const top = data?.top_keyword

  return (
    <section className="stats-card stats-hero" style={{
      background: 'linear-gradient(135deg, var(--color-surface) 0%, var(--color-surface) 60%, hsl(202, 45%, 97%) 100%)',
      border: '1.5px solid var(--color-line)',
      borderRadius: 'var(--radius)',
      padding: '40px 36px 38px',
      overflow: 'hidden',
    }}>
      <SectionHead num="01" label="今日" />

      <div className="stats-hero-body" style={{
        display: 'flex',
        justifyContent: 'flex-start',
        alignItems: 'flex-end',
        gap: 56,
        flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <div
            className="stats-hero-number stats-tabular"
            style={{
              fontFamily: "'IBM Plex Serif', 'Noto Serif SC', serif",
              fontSize: 88,
              fontWeight: 300,
              color: 'var(--color-text)',
              lineHeight: 0.95,
              letterSpacing: '-0.03em',
              display: 'flex',
              alignItems: 'baseline',
              gap: 10,
            }}
          >
            {hours > 0 && (
              <span>{hours}<span className="stats-hero-unit" style={UNIT_SM}>h</span></span>
            )}
            {(mins > 0 || hours === 0) && (
              <span>{mins}<span className="stats-hero-unit" style={UNIT_SM}>min</span></span>
            )}
          </div>
        </div>

        <div className="stats-hero-side" style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 18,
          textAlign: 'left',
          borderLeft: '1px solid var(--color-line)',
          paddingLeft: 28,
          minWidth: 160,
        }}>
          <div>
            <div style={ITEM_LABEL}>今日任务</div>
            <div
              className="stats-tabular"
              style={{
                fontFamily: "'IBM Plex Serif', serif",
                fontSize: 32,
                fontWeight: 300,
                color: 'var(--color-text)',
                lineHeight: 1,
              }}
            >
              {tasks}<span style={{ fontSize: 14, color: 'var(--color-subtle)', marginLeft: 4 }}>个</span>
            </div>
          </div>

          <div>
            <div style={ITEM_LABEL}>最常做的事</div>
            {top ? (
              <div style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                background: 'var(--color-surface)',
                border: '1px solid var(--color-primary)',
                color: 'hsl(202, 55%, 38%)',
                borderRadius: 99,
                padding: '6px 14px 6px 10px',
                fontSize: 13,
                fontWeight: 500,
                marginTop: 2,
              }}>
                <span style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: 'var(--color-primary)',
                }}></span>
                {top}
              </div>
            ) : (
              <div style={{ fontSize: 16, color: 'var(--color-muted)', marginTop: 6 }}>—</div>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
