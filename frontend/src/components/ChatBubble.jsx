/**
 * 聊天气泡组件。用户侧右对齐，小白侧左对齐 + 头像。
 * AI 侧消息可附带"记录/再聊聊"按钮（pendingTaskRec 时由 ChatPage 控制是否传入）。
 */

import stoatSrc from '../assets/stoat-front.svg'

export default function ChatBubble({ message, taskRec, onRecord, onDismiss }) {
  const isUser = message.role === 'user'

  return (
    <div style={{
      display: 'flex',
      justifyContent: isUser ? 'flex-end' : 'flex-start',
      gap: 8,
      marginBottom: 14,
      alignItems: 'flex-end',
    }}>
      {!isUser && <Avatar />}

      <div style={{ maxWidth: '75%' }}>
        <div style={{
          padding: '10px 14px',
          borderRadius: 14,
          fontSize: 14,
          lineHeight: 1.5,
          background: isUser ? 'var(--color-primary)' : 'var(--color-accent-soft)',
          color: isUser ? '#fff' : 'var(--color-text)',
          border: isUser ? '1px solid var(--color-primary)' : '1px solid var(--color-accent)',
          borderBottomRightRadius: isUser ? 4 : 14,
          borderBottomLeftRadius: isUser ? 14 : 4,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}>
          {message.content}
        </div>

        {/* 内联"记录/再聊聊"按钮——仅 AI 侧 + 有 taskRec 时 */}
        {!isUser && taskRec && (
          <div style={{ display: 'flex', gap: 8, marginTop: 8, paddingLeft: 4 }}>
            <button
              onClick={onRecord}
              style={{
                padding: '6px 14px',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--color-primary)',
                background: 'var(--color-primary)',
                color: '#fff',
                fontSize: 13,
                fontFamily: 'inherit',
                cursor: 'pointer',
              }}
            >
              记录「{taskRec.task_keyword}」
            </button>
            <button
              onClick={onDismiss}
              style={{
                padding: '6px 14px',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--color-line)',
                background: 'transparent',
                color: 'var(--color-subtle)',
                fontSize: 13,
                fontFamily: 'inherit',
                cursor: 'pointer',
              }}
            >
              再聊聊
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function Avatar() {
  // 小头像：用同一张 stoat SVG，容器 32x32 只露头部（约图高的 35%）
  return (
    <div style={{
      width: 32, height: 32, borderRadius: '50%',
      background: 'white',
      border: '1px solid var(--color-line)',
      flexShrink: 0,
      overflow: 'hidden',
      lineHeight: 0,
    }}>
      <img
        src={stoatSrc}
        alt="小白"
        style={{
          width: '120%',
          marginLeft: '-10%',
          marginTop: '-2%',
          display: 'block',
        }}
      />
    </div>
  )
}
