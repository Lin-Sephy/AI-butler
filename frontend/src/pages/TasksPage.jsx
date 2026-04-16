import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../lib/api.js'
import TaskCard from '../components/TaskCard.jsx'
import NewTaskModal from '../components/NewTaskModal.jsx'
import FocusOverlay from '../components/FocusOverlay.jsx'

export default function TasksPage() {
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showNewTask, setShowNewTask] = useState(false)
  const [focusTask, setFocusTask] = useState(null)
  const [completedOpen, setCompletedOpen] = useState(false)

  const fetchTasks = useCallback(async () => {
    try {
      const data = await apiFetch('/api/tasks/today')
      setTasks(data.tasks || [])
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

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
      await apiFetch(`/api/task/${taskId}/${action}`, { method: 'POST' })
      if (action === 'start') {
        await fetchTasks()
        const updated = (await apiFetch('/api/tasks/today')).tasks || []
        const started = updated.find(t => t.id === taskId && t.status === 'executing')
        if (started) setFocusTask(started)
      } else {
        setFocusTask(null)
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

  async function handleNewTask(data) {
    await apiFetch('/api/task/record', { method: 'POST', body: data })
    await fetchTasks()
  }

  // 分组
  const executing = tasks.filter(t => t.status === 'executing')
  const paused = tasks.filter(t => t.status === 'paused')
  const idle = tasks.filter(t => t.status === 'idle')
  const completed = tasks.filter(t => t.status === 'completed')
  const activeTasks = [...executing, ...paused, ...idle]

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

      {/* 顶部信息栏 */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
        marginBottom: 24,
      }}>
        <h1 style={{ fontSize: 28, fontWeight: 400 }}>任务</h1>
        <span style={{
          fontSize: 12, color: 'var(--color-subtle)',
          fontFamily: "'Inter', system-ui, sans-serif",
        }}>
          {executing.length > 0 && `执行中 ${executing.length}`}
          {idle.length > 0 && ` · 待完成 ${idle.length}`}
          {completed.length > 0 && ` · 已完成 ${completed.length}`}
        </span>
      </div>

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

      {/* 活跃任务列表 */}
      {activeTasks.length === 0 && completed.length === 0 ? (
        <div style={{
          padding: '56px 32px',
          textAlign: 'center',
          border: '1px dashed var(--color-accent)',
          borderRadius: 'var(--radius)',
          background: 'var(--color-surface)',
        }}>
          <p style={{
            fontSize: 17, color: 'var(--color-subtle)',
          }}>
            今天还没给自己安排点什么呢
          </p>
        </div>
      ) : (
        <>
          {activeTasks.map(t => (
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
    }}>
      {children}
    </div>
  )
}
