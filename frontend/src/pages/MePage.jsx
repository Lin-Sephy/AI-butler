/**
 * "我的"页 · v1 最小版（2026-04-23）
 *
 * 三个 section：
 *   - 账号状态 + 邮箱绑定（最小版：点按钮弹占位 Modal，上线前补完整 OTP flow）
 *   - 关于 + 版本号
 *   - 登出
 *
 * 完整版 backlog：
 *   - Modal 输邮箱 → supabase.auth.signInWithOtp → 输 OTP → 绑定成功
 *   - 错误态：邮箱格式错 / 已绑 / 验证失败 / rate limit
 *   - Supabase dashboard 配 OTP 邮件模板 + redirect URL
 */

import { useAuth } from '../contexts/AuthContext.jsx'
import { useConfirm } from '../contexts/ConfirmContext.jsx'
import { supabase } from '../lib/supabase.js'
import stoatSrc from '../assets/stoat-front.svg'

const APP_VERSION = 'v1.0.3'
const TAGLINE = '极简专注 · AI 陪伴'

export default function MePage() {
  const { user } = useAuth()
  const confirm = useConfirm()

  const email = user?.email || ''
  const isAnonymous = !email

  async function handleBindEmail() {
    // 最小版占位；上线前补完整 OTP flow
    await confirm({
      message: '绑邮箱功能即将开放\n现在先把小白用起来吧～',
      confirmText: '好',
      cancelText: '取消',
    })
  }

  async function handleLogout() {
    if (!await confirm('确定登出吗？')) return
    await supabase.auth.signOut()
    // onAuthStateChange 会自动触发 AuthContext 重新走匿名登录流程
  }

  return (
    <div>
      {/* 头部：头像 + 身份标签 */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        marginBottom: 28,
      }}>
        <Avatar />
        <div>
          <div style={{ fontSize: 17, color: 'var(--color-text)', marginBottom: 2 }}>
            {isAnonymous ? '游客账号' : email}
          </div>
          <div style={{ fontSize: 12, color: 'var(--color-subtle)' }}>
            {isAnonymous ? '还没绑邮箱，换设备会丢数据' : '已绑定邮箱'}
          </div>
        </div>
      </div>

      {/* 账号 section */}
      <Section title="账号">
        {isAnonymous && (
          <>
            <button
              onClick={handleBindEmail}
              style={primaryBtnStyle}
            >
              绑定邮箱
            </button>
            <p style={noteStyle}>
              绑邮箱后换设备不会丢数据
            </p>
          </>
        )}
        {!isAnonymous && (
          <p style={noteStyle}>
            数据会跟着邮箱走，换设备登录即可恢复
          </p>
        )}
      </Section>

      {/* 关于 section */}
      <Section title="关于">
        <div style={{ fontSize: 15, color: 'var(--color-text)', marginBottom: 4 }}>
          AI 小白 · {APP_VERSION}
        </div>
        <div style={noteStyle}>
          {TAGLINE}
        </div>
      </Section>

      {/* 登出 */}
      <div style={{ marginTop: 48 }}>
        <button
          onClick={handleLogout}
          style={logoutBtnStyle}
        >
          登出
        </button>
      </div>
    </div>
  )
}


// ════════════ UI helpers ════════════

function Avatar() {
  // 复用 ChatBubble 的头像样式：32x32 圆 + 白鼬正脸
  return (
    <div style={{
      width: 48, height: 48,
      borderRadius: '50%',
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

function Section({ title, children }) {
  return (
    <div style={{
      paddingTop: 20,
      paddingBottom: 20,
      borderTop: '1px solid var(--color-line)',
    }}>
      <div style={{
        fontSize: 12,
        color: 'var(--color-subtle)',
        marginBottom: 12,
        letterSpacing: '0.04em',
      }}>
        {title}
      </div>
      {children}
    </div>
  )
}

const primaryBtnStyle = {
  padding: '10px 20px',
  borderRadius: 'var(--radius)',
  border: '1px solid var(--color-primary)',
  background: 'var(--color-primary)',
  color: '#fff',
  fontSize: 14,
  fontFamily: 'inherit',
  cursor: 'pointer',
  transition: 'var(--transition) ease-out',
}

const logoutBtnStyle = {
  padding: '10px 20px',
  borderRadius: 'var(--radius)',
  border: '1px solid var(--color-line)',
  background: 'transparent',
  color: 'var(--color-subtle)',
  fontSize: 14,
  fontFamily: 'inherit',
  cursor: 'pointer',
  transition: 'var(--transition) ease-out',
}

const noteStyle = {
  fontSize: 12,
  color: 'var(--color-subtle)',
  margin: '8px 0 0',
  lineHeight: 1.5,
}
