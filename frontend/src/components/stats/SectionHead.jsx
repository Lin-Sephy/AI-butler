/**
 * 数据页 · Section Head · 编号 + 细分隔线 + 标题 + 右侧扩展槽
 * 四个 section 共用。
 */

export default function SectionHead({ num, label, extra }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 14,
      marginBottom: 24,
    }}>
      <span
        className="stats-tabular"
        style={{
          fontFamily: "'IBM Plex Serif', serif",
          fontSize: 11,
          fontWeight: 500,
          color: 'var(--color-primary)',
          letterSpacing: '0.1em',
          paddingTop: 1,
        }}
      >{num}</span>
      <span style={{
        width: 24,
        height: 1,
        background: 'var(--color-line)',
      }}></span>
      <span style={{
        fontSize: 14,
        fontWeight: 400,
        color: 'var(--color-text)',
        letterSpacing: '0.04em',
      }}>{label}</span>
      {extra && <div style={{ marginLeft: 'auto' }}>{extra}</div>}
    </div>
  )
}
