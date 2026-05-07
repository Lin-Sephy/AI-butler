import { Fragment } from 'react'

export function cleanAssistantText(text) {
  if (!text) return ''
  return String(text)
    .replace(/\*\*([^*\n]+)\*\*/g, '$1')
    .replace(/__([^_\n]+)__/g, '$1')
    .replace(/`([^`\n]+)`/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
}

export function renderAssistantText(text) {
  const source = String(text || '').replace(/^#{1,6}\s+/gm, '')
  const parts = []
  const pattern = /(\*\*([^*\n]+)\*\*|__([^_\n]+)__|`([^`\n]+)`)/g
  let lastIndex = 0
  let match

  while ((match = pattern.exec(source)) !== null) {
    if (match.index > lastIndex) {
      parts.push(source.slice(lastIndex, match.index))
    }

    const boldText = match[2] || match[3]
    const codeText = match[4]
    if (boldText) {
      parts.push(boldText)
    } else {
      parts.push(codeText)
    }
    lastIndex = pattern.lastIndex
  }

  if (lastIndex < source.length) {
    parts.push(source.slice(lastIndex))
  }

  return parts.map((part, i) => (
    <Fragment key={i}>{part}</Fragment>
  ))
}
