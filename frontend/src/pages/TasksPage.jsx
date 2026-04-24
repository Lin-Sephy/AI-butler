import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../lib/api.js'
import TaskCard from '../components/TaskCard.jsx'
import NewTaskModal from '../components/NewTaskModal.jsx'
import FocusOverlay from '../components/FocusOverlay.jsx'

export default function TasksPage() {
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(false)
  const [firstLoad, setFirstLoad] = useState(true)
  const [error, setError] = useState(null)
  const [showNewTask, setShowNewTask] = useState(false)
  const [focusTask, setFocusTask] = useState(null)
  const [completedOpen, setCompletedOpen] = useState(false)
  const [abandonedOpen, setAbandonedOpen] = useState(false)

  const fetchTasks = useCallback(async () => {
    if (firstLoad) setLoading(true)
    try {
      const data = await apiFetch('/api/tasks/today')
      setTasks(data.tasks || [])
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
      setFirstLoad(false)
    }
  }, [firstLoad])

  useEffect(() => { fetchTasks() }, [fetchTasks])

  // 正在专注中的任务检测
  useEffect(() => {
    const executing = tasks.find(t => t.status === 'executing')
    if (executing && !focusTask) {
      setFocusTask(executing)
    }
  }, [tasks])

  async function handleAction(action, taskId) {
    try {
      const res = await apiFetch(`/api/task/${taskId}/${action}`, { method: 'POST' })
      if (action === 'start') {
        // POST 返回的 task 已是 executing，直接进 FocusOverlay，不再重查一次
        if (res?.task?.status === 'executing') setFocusTask(res.task)
        fetchTasks()
      } else {
        setFocusTask(null)
        setTasks(prev => prev.map(t => t.id === taskId ? { ...t, status: action === 'complete' ? 'completed' : action === 'abandon' ? 'abandoned' : t.status } : t))
        await fetchTasks()
      }
    } catch (e) {
      alert(e.message)
    }
  }

  async function handleDelete(taskId) {
    try {
      await apiFetch(`/api/task/${taskId}`, { method: 'DELETE' })
      await fetchTasks()
    } catch (e) {
      alert(e.message)
    }
  }

  async function handleRestore(taskId) {
    try {
      await apiFetch(`/api/task/${taskId}/restore`, { method: 'POST' })
      await fetchTasks()
    } catch (e) {
      alert(e.message)
    }
  }

  async function handleNewTask(data) {
    const { task_keyword, suggested_minutes, recurring } = data
    if (recurring) {
      await apiFetch('/api/recurring', { method: 'POST', body: {
        keyword: task_keyword,
        default_minutes: suggested_minutes,
      }})
    } else {
      await apiFetch('/api/task/record', { method: 'POST', body: data })
    }
    await fetchTasks()
  }

  // 分组
  const pad = n => String(n).padStart(2, '0')
  const now = new Date()
  const todayStr = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`

  const unscheduled = tasks.filter(t =>
    !t.scheduled_at && ['idle', 'paused', 'executing'].includes(t.status)
  )
  const allScheduled = tasks
    .filter(t => t.scheduled_at && ['idle', 'scheduled', 'paused', 'executing'].includes(t.status))
    .sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at))
  const todayScheduled = allScheduled.filter(t => t.scheduled_at.slice(0, 10) === todayStr)
  const futureScheduled = allScheduled.filter(t => t.scheduled_at.slice(0, 10) > todayStr)

  const futureByDate = {}
  futureScheduled.forEach(t => {
    const d = t.scheduled_at.slice(0, 10)
    if (!futureByDate[d]) futureByDate[d] = []
    futureByDate[d].push(t)
  })

  const completed = tasks.filter(t => t.status === 'completed')
  const abandoned = tasks.filter(t => t.status === 'abandoned')
  const hasActive = unscheduled.length > 0 || allScheduled.length > 0

  if (loading) {
    return <CenterText>加载中…</CenterText>
  }

  return (
    <>
      {/* 专注遮罩 */}
      {focusTask && (
        <FocusOverlay
          task={focusTask}
          onComplete={id => handleAction('complete', id)}
          onAbandon={id => handleAction('abandon', id)}
        />
      )}

      <h1 style={{ fontSize: 28, fontWeight: 400, marginBottom: 24 }}>任务</h1>

      {error && (
        <div style={{
          padding: '12px 16px', marginBottom: 16,
          borderRadius: 'var(--radius)',
          background: '#fee', border: '1px solid #fbb',
          fontSize: 13, color: '#933',
        }}>
          {error}
        </div>
      )}

      {!hasActive && completed.length === 0 && abandoned.length === 0 ? (
        <div style={{
          padding: '56px 32px',
          textAlign: 'center',
          border: '1px dashed var(--color-accent)',
          borderRadius: 'var(--radius)',
          background: 'var(--color-surface)',
        }}>
          <p style={{ fontSize: 17, color: 'var(--color-subtle)' }}>
            今天还没给自己安排点什么呢
          </p>
        </div>
      ) : (
        <>
          {/* 未定时任务 */}
          {unscheduled.map(t => (
            <TaskCard
              key={t.id}
              task={t}
              onStart={id => handleAction('start', id)}
              onPause={id => handleAction('pause', id)}
              onResume={id => handleAction('resume', id)}
              onComplete={id => handleAction('complete', id)}
              onAbandon={id => handleAction('abandon', id)}
              onDelete={handleDelete}
            />
          ))}

          {/* 今天的预定任务 — 时间轴 */}
          {todayScheduled.length > 0 && (
            <TimelineSection tasks={todayScheduled} cardHandlers={{
              onStart: id => handleAction('start', id),
              onPause: id => handleAction('pause', id),
              onResume: id => handleAction('resume', id),
              onComplete: id => handleAction('complete', id),
              onAbandon: id => handleAction('abandon', id),
              onDelete: handleDelete,
            }} />
          )}

          {/* 未来日期的预定任务 */}
          {Object.keys(futureByDate).sort().map(dateKey => (
            <div key={dateKey}>
              <DateDivider date={dateKey} today={todayStr} />
              <TimelineSection tasks={futureByDate[dateKey]} cardHandlers={{
                onStart: id => handleAction('start', id),
                onPause: id => handleAction('pause', id),
                onResume: id => handleAction('resume', id),
                onComplete: id => handleAction('complete', id),
                onAbandon: id => handleAction('abandon', id),
                onDelete: handleDelete,
              }} />
            </div>
          ))}

          {/* 已完成折叠 */}
          {completed.length > 0 && (
            <>
              <button
                onClick={() => setCompletedOpen(!completedOpen)}
                style={{
                  marginTop: 8,
                  padding: '8px 0',
                  background: 'transparent', border: 'none',
                  color: 'var(--color-subtle)',
                  fontSize: 13, fontFamily: 'inherit',
                  cursor: 'pointer',
                }}
              >
                今日完成 {completed.length} 个 {completedOpen ? '▲' : '▼'}
              </button>
              {completedOpen && completed.map(t => (
                <TaskCard
                  key={t.id}
                  task={t}
                  onStart={() => {}}
                  onPause={() => {}}
                  onResume={() => {}}
                  onComplete={() => {}}
                  onAbandon={() => {}}
                  onDelete={handleDelete}
                />
              ))}
            </>
          )}

          {/* 已放弃折叠 · 2 天内可恢复 · 2 天后自动消失 */}
          {abandoned.length > 0 && (
            <>
              <button
                onClick={() => setAbandonedOpen(!abandonedOpen)}
                style={{
                  marginTop: 4,
                  padding: '8px 0',
                  background: 'transparent', border: 'none',
                  color: 'var(--color-muted)',
                  fontSize: 13, fontFamily: 'inherit',
                  cursor: 'pointer',
                }}
              >
                已放弃 {abandoned.length} 个 {abandonedOpen ? '▲' : '▼'}
              </button>
              {abandonedOpen && abandoned.map(t => (
                <TaskCard
                  key={t.id}
                  task={t}
                  onStart={() => {}}
                  onPause={() => {}}
                  onResume={() => {}}
                  onComplete={() => {}}
                  onAbandon={() => {}}
                  onRestore={handleRestore}
                  onDelete={handleDelete}
                />
              ))}
            </>
          )}
        </>
      )}

      {/* 新建任务按钮（永远跟在列表末尾或空状态后面） */}
      <button
        onClick={() => setShowNewTask(true)}
        style={{
          marginTop: 16,
          width: '100%',
          padding: '14px 20px',
          borderRadius: 'var(--radius)',
          border: '1px dashed var(--color-line)',
          background: 'transparent',
          color: 'var(--color-subtle)',
          fontSize: 15, fontFamily: 'inherit',
          cursor: 'pointer',
          textAlign: 'left',
          transition: 'var(--transition) ease-out',
        }}
        onMouseEnter={e => {
          e.currentTarget.style.borderColor = 'var(--color-primary)'
          e.currentTarget.style.color = 'var(--color-primary)'
          e.currentTarget.style.background = 'var(--color-primary-soft)'
        }}
        onMouseLeave={e => {
          e.currentTarget.style.borderColor = 'var(--color-line)'
          e.currentTarget.style.color = 'var(--color-subtle)'
          e.currentTarget.style.background = 'transparent'
        }}
      >
        + 新建任务
      </button>

      {/* 新建任务弹窗 */}
      {showNewTask && (
        <NewTaskModal
          onSubmit={handleNewTask}
          onClose={() => setShowNewTask(false)}
        />
      )}
    </>
  )
}

function CenterText({ children }) {
  return (
    <div style={{
      padding: '80px 0', textAlign: 'center',
      color: 'var(--color-subtle)',
      fontSize: 14,
    }}>
      {children}
    </div>
  )
}

function TimelineSection({ tasks, cardHandlers }) {
  return (
    <div style={{ position: 'relative', paddingLeft: 24, marginTop: 8 }}>
      {/* 竖线 center = 5px from left edge */}
      <div style={{
        position: 'absolute', left: 4, top: 20, bottom: 12,
        width: 2, background: 'var(--color-primary)', opacity: 0.25,
        borderRadius: 1,
      }} />
      {tasks.map((t, i) => {
        const m = t.scheduled_at?.match(/T(\d{2}):(\d{2})/)
        const hhmm = m ? `${m[1]}:${m[2]}` : ''
        return (
          <div key={t.id} style={{ position: 'relative' }}>
            {/* 圆点 center = paddingLeft(24) 外的 0px + left(-24) + width(10)/2 = -19px → 用 left:0 绝对定位到容器 */}
            <div style={{
              position: 'absolute', left: -24,
              top: hhmm ? 40 : 22,
              width: 10, height: 10, borderRadius: '50%',
              marginLeft: 0,
              background: t.status === 'executing' ? 'var(--color-primary)' : 'transparent',
              border: '2px solid var(--color-primary)',
              zIndex: 1,
            }} />
            {hhmm && (
              <div style={{
                fontSize: 12, color: 'var(--color-subtle)',
                fontFamily: "'Inter', system-ui, sans-serif",
                marginBottom: 4, marginTop: i > 0 ? 4 : 0,
              }}>
                {hhmm}
              </div>
            )}
            <TaskCard task={t} hideTime {...cardHandlers} />
          </div>
        )
      })}
    </div>
  )
}

function DateDivider({ date, today }) {
  const pad = n => String(n).padStart(2, '0')
  const tomorrow = new Date()
  tomorrow.setDate(tomorrow.getDate() + 1)
  const tmrStr = `${tomorrow.getFullYear()}-${pad(tomorrow.getMonth() + 1)}-${pad(tomorrow.getDate())}`
  let label
  if (date === tmrStr) label = '明天'
  else label = date.slice(5)
  return (
    <div style={{
      fontSize: 13, color: 'var(--color-subtle)',
      margin: '20px 0 4px',
      fontFamily: "'Inter', system-ui, sans-serif",
    }}>
      {label}
    </div>
  )
}
