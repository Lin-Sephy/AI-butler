/**
 * BYOK：用户自带 LLM API key 配置 · v5.0（2026-04-22）
 *
 * 放在 SettingsPanel 的"API key"区块。四个字段：
 *   - 服务商下拉（DeepSeek / OpenAI / 智谱 / 硅基流动 / 其他）
 *   - Base URL（选服务商时自动填，用户可改）
 *   - Model（每个服务商有候选，用户可选或自填）
 *   - API Key（掩码展示，点击清空可重输）
 *
 * 自带独立的"保存 / 清空"按钮——不走父组件 SettingsPanel 的统一保存。
 * 因为密钥是敏感信息，操作要独立明确。
 *
 * API 端点（后端 api.py）：
 *   GET  /api/profile/llm  → {provider, base_url, model, api_key_hint, has_key}
 *   PUT  /api/profile/llm  body {provider, base_url, model, api_key}
 *                          api_key 空串 = 不更新原值；非空 = 替换
 *   DELETE /api/profile/llm → 清空所有 llm_* 字段，回退默认
 */

import { useEffect, useState } from 'react'
import { apiFetch } from '../lib/api.js'

// 预设服务商。key 用英文 id，label 是下拉展示名。
const PROVIDERS = {
  deepseek: {
    label: 'DeepSeek',
    base_url: 'https://api.deepseek.com',
    models: ['deepseek-chat', 'deepseek-reasoner'],
  },
  openai: {
    label: 'OpenAI',
    base_url: 'https://api.openai.com/v1',
    models: ['gpt-4o', 'gpt-5', 'gpt-4o-mini', 'gpt-5-mini'],
  },
  zhipu: {
    label: '智谱',
    base_url: 'https://open.bigmodel.cn/api/paas/v4',
    models: ['glm-4', 'glm-4-flash', 'glm-4.5'],
  },
  silicon: {
    label: '硅基流动',
    base_url: 'https://api.siliconflow.cn/v1',
    models: ['deepseek-ai/DeepSeek-V3', 'Qwen/Qwen2.5-72B-Instruct'],
  },
  custom: {
    label: '其他（自填）',
    base_url: '',
    models: [],
  },
}

const PROVIDER_ORDER = ['deepseek', 'openai', 'zhipu', 'silicon', 'custom']


export default function LlmConfig() {
  // 后端返回的状态
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)

  // 表单状态
  const [provider, setProvider] = useState('deepseek')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [apiKeyInput, setApiKeyInput] = useState('')     // 用户刚输入的新 key；空表示不改
  const [apiKeyHint, setApiKeyHint] = useState('')       // 后端返的掩码字符串
  const [hasKey, setHasKey] = useState(false)

  // 操作状态
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState(null)           // 成功提示
  const [saveError, setSaveError] = useState(null)

  useEffect(() => {
    apiFetch('/api/profile/llm')
      .then(data => {
        setProvider(data.provider || 'deepseek')
        setBaseUrl(data.base_url || '')
        setModel(data.model || '')
        setApiKeyHint(data.api_key_hint || '')
        setHasKey(!!data.has_key)
      })
      .catch(e => setLoadError(e.message || '加载失败'))
      .finally(() => setLoading(false))
  }, [])

  // 切服务商 → 如果当前是空或跟某预设匹配，自动填 base_url / model
  function handleChangeProvider(next) {
    setProvider(next)
    const preset = PROVIDERS[next]
    if (!preset) return
    // 只在 base_url 为空或属于其他预设时才覆盖，避免抹掉用户自填的
    const knownBaseUrls = Object.values(PROVIDERS).map(p => p.base_url).filter(Boolean)
    if (!baseUrl || knownBaseUrls.includes(baseUrl)) {
      setBaseUrl(preset.base_url)
    }
    // model：如果当前 model 不在新 provider 的候选里，清空让用户选
    if (preset.models.length > 0 && !preset.models.includes(model)) {
      setModel(preset.models[0])
    }
  }

  async function handleSave() {
    if (saving) return
    setSaving(true)
    setSaveMsg(null)
    setSaveError(null)
    try {
      const body = {
        provider: provider.trim(),
        base_url: baseUrl.trim(),
        model: model.trim(),
        api_key: apiKeyInput.trim(),   // 空串 = 不改 api_key，非空 = 更新
      }
      const resp = await apiFetch('/api/profile/llm', { method: 'PUT', body })
      setApiKeyHint(resp.api_key_hint || '')
      setHasKey(!!resp.has_key)
      setApiKeyInput('')   // 清空输入框，下次保存时用户要再输才算改
      setSaveMsg('已保存')
      setTimeout(() => setSaveMsg(null), 1800)
    } catch (e) {
      setSaveError(e.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  async function handleClear() {
    if (!window.confirm('清空自带配置，回到用默认服务？')) return
    setSaving(true)
    setSaveError(null)
    try {
      await apiFetch('/api/profile/llm', { method: 'DELETE' })
      setProvider('deepseek')
      setBaseUrl('')
      setModel('')
      setApiKeyInput('')
      setApiKeyHint('')
      setHasKey(false)
      setSaveMsg('已清空')
      setTimeout(() => setSaveMsg(null), 1800)
    } catch (e) {
      setSaveError(e.message || '清空失败')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div style={{ fontSize: 13, color: 'var(--color-subtle)', padding: '8px 0' }}>
      加载中…
    </div>
  }

  if (loadError) {
    return <div style={{ fontSize: 13, color: '#933', padding: '8px 0' }}>
      加载失败：{loadError}
    </div>
  }

  const currentPreset = PROVIDERS[provider] || PROVIDERS.custom
  const modelOptions = currentPreset.models

  return (
    <div>
      {/* 服务商 */}
      <Label>服务商</Label>
      <select
        value={provider}
        onChange={e => handleChangeProvider(e.target.value)}
        style={selectStyle}
      >
        {PROVIDER_ORDER.map(key => (
          <option key={key} value={key}>{PROVIDERS[key].label}</option>
        ))}
      </select>

      {/* Base URL */}
      <Label>Base URL</Label>
      <input
        value={baseUrl}
        onChange={e => setBaseUrl(e.target.value)}
        placeholder="https://..."
        style={inputStyle}
      />

      {/* Model */}
      <Label>Model</Label>
      {modelOptions.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {modelOptions.map(m => (
              <MiniChip key={m} selected={m === model} onClick={() => setModel(m)}>
                {m}
              </MiniChip>
            ))}
          </div>
          <input
            value={model}
            onChange={e => setModel(e.target.value)}
            placeholder="或自填 model 名"
            style={{ ...inputStyle, marginTop: 0 }}
          />
        </div>
      ) : (
        <input
          value={model}
          onChange={e => setModel(e.target.value)}
          placeholder="model 名（如 gpt-5）"
          style={inputStyle}
        />
      )}

      {/* API Key */}
      <Label>API Key</Label>
      <input
        type="password"
        value={apiKeyInput}
        onChange={e => setApiKeyInput(e.target.value)}
        placeholder={hasKey ? `${apiKeyHint}（已保存，输入新值替换）` : '粘贴你的 API key'}
        style={inputStyle}
        autoComplete="off"
      />

      {/* 底部操作 */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
        gap: 10, marginTop: 12,
      }}>
        {saveMsg && !saveError && (
          <span style={{ fontSize: 12, color: 'var(--color-subtle)', flex: 1 }}>{saveMsg}</span>
        )}
        {saveError && (
          <span style={{ fontSize: 12, color: '#933', flex: 1 }}>{saveError}</span>
        )}
        {hasKey && (
          <button
            type="button"
            onClick={handleClear}
            disabled={saving}
            style={secondaryBtnStyle}
          >
            清空
          </button>
        )}
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          style={{
            ...primaryBtnStyle,
            cursor: saving ? 'wait' : 'pointer',
            opacity: saving ? 0.5 : 1,
          }}
        >
          {saving ? '保存中…' : '保存'}
        </button>
      </div>
    </div>
  )
}


// ════════════ 小组件 ════════════

function Label({ children }) {
  return (
    <div style={{
      fontSize: 12, color: 'var(--color-subtle)',
      marginTop: 10, marginBottom: 4,
    }}>
      {children}
    </div>
  )
}

function MiniChip({ selected, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: '4px 10px',
        borderRadius: 999,
        border: `1px solid ${selected ? 'var(--color-primary)' : 'var(--color-line)'}`,
        background: selected ? 'var(--color-primary-soft)' : 'transparent',
        color: selected ? 'var(--color-primary)' : 'var(--color-subtle)',
        fontSize: 11, fontFamily: "'Inter', system-ui, sans-serif",
        cursor: 'pointer',
        transition: 'var(--transition) ease-out',
      }}
    >
      {children}
    </button>
  )
}


// ════════════ 样式 ════════════

const inputStyle = {
  width: '100%',
  padding: '8px 12px',
  borderRadius: 'var(--radius)',
  border: '1px solid var(--color-line)',
  background: 'var(--color-surface)',
  font: 'inherit',
  color: 'var(--color-text)',
  outline: 'none',
  boxSizing: 'border-box',
  fontSize: 13,
}

const selectStyle = {
  ...inputStyle,
  cursor: 'pointer',
}

const primaryBtnStyle = {
  padding: '8px 20px',
  borderRadius: 'var(--radius)',
  border: '1px solid var(--color-primary)',
  background: 'var(--color-primary)',
  color: '#fff',
  fontSize: 13, fontFamily: 'inherit',
}

const secondaryBtnStyle = {
  padding: '8px 16px',
  borderRadius: 'var(--radius)',
  border: '1px solid var(--color-line)',
  background: 'transparent',
  color: 'var(--color-subtle)',
  fontSize: 13, fontFamily: 'inherit',
  cursor: 'pointer',
}
