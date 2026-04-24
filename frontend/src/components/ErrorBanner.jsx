export default function ErrorBanner({ children }) {
  return (
    <div style={{
      padding: '10px 14px', marginBottom: 12,
      borderRadius: 'var(--radius)',
      background: '#fee', border: '1px solid #fbb',
      fontSize: 13, color: '#933',
      position: 'relative', zIndex: 1,
    }}>{children}</div>
  )
}
