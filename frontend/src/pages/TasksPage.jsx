import { useState, useEffect, useCallback, useRef } from 'react'
import { apiFetch } from '../lib/api.js'
import { useToast } from '../contexts/ToastContext.jsx'
import TaskCard from '../components/TaskCard.jsx'
import NewTaskModal from '../components/NewTaskModal.jsx'
import FocusOverlay from '../components/FocusOverlay.jsx'
import { readLocalBool, writeLocalBool } from '../lib/localPrefs.js'

const TASK_DAY_START_HOUR = 4
const COMPLETED_OPEN_KEY = 'ai-butler-tasks-completed-open'
const ABANDONED_OPEN_KEY = 'ai-butler-tasks-abandoned-open'

export default function TasksPage() {
  const showToast = useToast()
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(false)
  const [firstLoad, setFirstLoad] = useState(true)
  const [error, setError] = useState(null)
  const [showNewTask, setShowNewTask] = useState(false)
  const [focusTask, setFocusTask] = useState(null)
  const focusSyncRef = useRef(Promise.resolve())
  const [completedOpen, setCompletedOpenRaw] = useState(() => readLocalBool(COMPLETED_OPEN_KEY))
  const [abandonedOpen, setAbandonedOpenRaw] = useState(() => readLocalBool(ABANDONED_OPEN_KEY))

  function setCompletedOpen(next) {
    setCompletedOpenRaw(next)
    writeLocalBool(COMPLETED_OPEN_KEY, next)
  }

  function setAbandonedOpen(next) {
    setAbandonedOpenRaw(next)
    writeLocalBool(ABANDONED_OPEN_KEY, next)
  }

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

  function queueFocusRequest(request) {
    const next = focusSyncRef.current
      .catch(() => {})
      .then(request)
    focusSyncRef.current = next
    return next
  }

  async function handleAction(action, taskId, payload) {
    let originalStartTask = null
    let optimisticStartTask = null
    if (action === 'start') {
      const currentTask = tasks.find(t => t.id === taskId)
      if (currentTask) {
        originalStartTask = currentTask
        optimisticStartTask = {
          ...currentTask,
          status: 'executing',
          started_at: new Date().toISOString(),
        }
        setFocusTask(optimisticStartTask)
        setTasks(prev => prev.map(t => t.id === taskId ? optimisticStartTask : t))
      }
    } else if (action === 'complete' || action === 'abandon') {
      setFocusTask(null)
      setTasks(prev => prev.map(t => (
        t.id === taskId
          ? { ...t, status: action === 'complete' ? 'completed' : 'abandoned' }
          : t
      )))
    }

    try {
      const request = () => apiFetch(`/api/task/${taskId}/${action}`, {
        method: 'POST',
        body: payload || undefined,
      })
      const res = await (
        ['start', 'complete', 'abandon'].includes(action)
          ? queueFocusRequest(request)
          : request()
      )
      if (action === 'start') {
        // 前端已先开 FocusOverlay；后端返回后更新任务事实，当前遮罩仍沿用本地开始时间。
        if (res?.task?.status === 'executing') {
          setFocusTask(res.task)
          setTasks(prev => prev.map(t => t.id === taskId ? res.task : t))
        }
        fetchTasks()
      } else {
        await fetchTasks()
      }
    } catch (e) {
      if (action === 'start') {
        setFocusTask(null)
        if (originalStartTask) {
          setTasks(prev => prev.map(t => t.id === taskId ? originalStartTask : t))
        }
        fetchTasks()
      } else if (action === 'complete' || action === 'abandon') {
        fetchTasks()
      }
      showToast(e.message)
    }
  }

  async function handleFocusPause(taskId) {
    const res = await queueFocusRequest(
      () => apiFetch(`/api/task/${taskId}/pause`, { method: 'POST' }),
    )
    if (res?.task) {
      setTasks(prev => prev.map(t => t.id === taskId ? res.task : t))
      if (res.task.status === 'paused') setFocusTask(res.task)
    }
    return res?.task
  }

  async function handleFocusResume(taskId, payload) {
    const res = await queueFocusRequest(
      () => apiFetch(`/api/task/${taskId}/resume`, {
        method: 'POST',
        body: payload || {},
      }),
    )
    if (res?.task) {
      setTasks(prev => prev.map(t => t.id === taskId ? res.task : t))
      if (res.task.status === 'executing') setFocusTask(res.task)
    }
    return res?.task
  }

  async function handleFocusComplete(taskId, payload) {
    return handleAction('complete', taskId, payload)
  }

  async function handleDelete(taskId) {
    try {
      await apiFetch(`/api/task/${taskId}`, { method: 'DELETE' })
      await fetchTasks()
    } catch (e) {
      showToast(e.message)
    }
  }

  async function handleStopRecurring(taskId) {
    try {
      await apiFetch(`/api/task/${taskId}/recurring`, { method: 'DELETE' })
      await fetchTasks()
    } catch (e) {
      showToast(e.message)
    }
  }

  async function handleRestore(taskId) {
    try {
      await apiFetch(`/api/task/${taskId}/restore`, { method: 'POST' })
      await fetchTasks()
    } catch (e) {
      showToast(e.message)
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
  const todayStr = getTaskDayKey()

  const unscheduled = tasks.filter(t =>
    !t.scheduled_at && ['idle', 'paused', 'executing'].includes(t.status)
  )
  const allScheduled = tasks
    .filter(t => t.scheduled_at && ['idle', 'scheduled', 'paused', 'executing'].includes(t.status))
    .sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at))
  const todayScheduled = allScheduled.filter(t => getTaskDayKeyFromIso(t.scheduled_at) === todayStr)
  const futureScheduled = allScheduled.filter(t => getTaskDayKeyFromIso(t.scheduled_at) > todayStr)

  const futureByDate = {}
  futureScheduled.forEach(t => {
    const d = getTaskDayKeyFromIso(t.scheduled_at)
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
          onPause={handleFocusPause}
          onResume={handleFocusResume}
          onComplete={handleFocusComplete}
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
              onStopRecurring={handleStopRecurring}
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
              onStopRecurring: handleStopRecurring,
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
                onStopRecurring: handleStopRecurring,
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
  const tomorrow = parseDateKey(today)
  tomorrow.setDate(tomorrow.getDate() + 1)
  const tmrStr = formatDateKey(tomorrow)
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

function pad(n) {
  return String(n).padStart(2, '0')
}

function formatDateKey(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function parseDateKey(key) {
  const [year, month, day] = key.split('-').map(Number)
  return new Date(year, month - 1, day)
}

function getTaskDayKey(date = new Date()) {
  const d = new Date(date)
  if (d.getHours() < TASK_DAY_START_HOUR) d.setDate(d.getDate() - 1)
  return formatDateKey(d)
}

function getTaskDayKeyFromIso(iso) {
  if (!iso) return ''
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2})/)
  if (!m) return iso.slice(0, 10)
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  if (Number(m[4]) < TASK_DAY_START_HOUR) d.setDate(d.getDate() - 1)
  return formatDateKey(d)
}
