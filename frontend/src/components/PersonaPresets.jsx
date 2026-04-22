/**
 * 性格预设按钮组件 · v5.0
 *
 * 三个预设模板按钮，点击后把对应文字填进父组件的 textarea。
 * 故意不出现 INFP/INTJ/INTP 字样，只用"预设 N + 一句摘要"命名——
 * 因为用户点完可以自由编辑，身份标签会骗人。
 *
 * 以后如果要彻底砍 MBTI 预设：父组件 SettingsPanel 里把 <PersonaPresets />
 * 一行删掉即可，textarea 照常工作。
 *
 * props:
 *   - currentText: string — 当前 textarea 内容，用来判断是否需要 confirm 覆盖
 *   - onPick(text: string) — 用户选中某个预设后调回，由父组件覆盖 textarea
 */

import { useEffect, useState } from 'react'
import { apiFetch } from '../lib/api.js'

// 摘要词写死在前端：后端 PERSONAS 顺序是 infp/intj/intp，对齐展示成"预设 1/2/3"
const SUMMARIES = {
  infp: '共情陪伴',
  intj: '高效拆解',
  intp: '观察点破',
}

const DISPLAY_ORDER = ['infp', 'intj', 'intp']

export default function PersonaPresets({ currentText, onPick }) {
  const [presets, setPresets] = useState(null)  // { infp: "...", intj: "...", intp: "..." }
  const [error, setError] = useState(null)

  useEffect(() => {
    apiFetch('/api/profile/persona_presets')
      .then(data => {
        const map = {}
        for (const p of data.presets || []) map[p.key] = p.text
        setPresets(map)
      })
      .catch(e => setError(e.message))
  }, [])

  function handlePick(key) {
    if (!presets) return
    const text = presets[key]
    if (!text) return

    // 非空 textarea 才提醒；如果当前已经是这段预设原文，也直接重填（等价空操作）
    if (currentText.trim() && currentText !== text) {
      if (!window.confirm('会覆盖当前性格描述，确定？')) return
    }
    onPick(text)
  }

  if (error) {
    return <div style={{ fontSize: 12, color: 'var(--color-subtle)', marginBottom: 8 }}>
      预设加载失败：{error}
    </div>
  }

  return (
    <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
      {DISPLAY_ORDER.map((key, i) => {
        const loaded = presets !== null
        const disabled = !loaded
        return (
          <button
            key={key}
            type="button"
            disabled={disabled}
            onClick={() => handlePick(key)}
            style={{
              flex: 1,
              padding: '10px 8px',
              borderRadius: 'var(--radius)',
              border: '1px solid var(--color-accent)',
              background: 'var(--color-accent-soft)',
              color: 'var(--color-primary)',
              fontFamily: 'inherit',
              cursor: disabled ? 'wait' : 'pointer',
              opacity: disabled ? 0.5 : 1,
              transition: 'var(--transition) ease-out',
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3,
            }}
            onMouseEnter={e => {
              if (disabled) return
              e.currentTarget.style.borderColor = 'var(--color-primary)'
              e.currentTarget.style.background = 'var(--color-primary-soft)'
            }}
            onMouseLeave={e => {
              if (disabled) return
              e.currentTarget.style.borderColor = 'var(--color-accent)'
              e.currentTarget.style.background = 'var(--color-accent-soft)'
            }}
          >
            <span style={{ fontSize: 13 }}>预设 {i + 1}</span>
            <span style={{ fontSize: 11, color: 'var(--color-subtle)' }}>
              {SUMMARIES[key]}
            </span>
          </button>
        )
      })}
    </div>
  )
}
