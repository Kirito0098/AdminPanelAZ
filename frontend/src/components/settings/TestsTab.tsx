import { useEffect, useState } from 'react'
import { FlaskConical, Play, RefreshCw } from 'lucide-react'
import { ApiError, collectTests, getTestTask, runTests } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { useNotifications } from '@/context/NotificationContext'

interface TestItem {
  id: string
  title: string
  description?: string
}

export default function TestsTab() {
  const { success, error: notifyError } = useNotifications()
  const [tests, setTests] = useState<TestItem[]>([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [taskStatus, setTaskStatus] = useState<string>('')
  const [result, setResult] = useState<string>('')

  const load = async () => {
    setLoading(true)
    try {
      const data = await collectTests()
      setTests(data.tests || [])
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сбора тестов')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  useEffect(() => {
    if (!taskId || !running) return
    const timer = setInterval(async () => {
      try {
        const task = await getTestTask(taskId)
        setTaskStatus(`${task.progress_stage} (${task.progress_percent}%)`)
        if (task.status === 'completed' || task.status === 'failed') {
          setRunning(false)
          const res = task.result as { message?: string; raw_output?: string } | undefined
          setResult(res?.raw_output || res?.message || task.message)
          if (task.status === 'completed') success('Тесты завершены')
          else notifyError(task.error || 'Тесты завершились с ошибкой')
        }
      } catch {
        /* ignore poll errors */
      }
    }, 1500)
    return () => clearInterval(timer)
  }, [taskId, running])

  const handleRun = async (testIds: string[] = []) => {
    setRunning(true)
    setResult('')
    try {
      const data = await runTests(testIds)
      setTaskId(data.task_id)
      setTaskStatus('Запуск...')
    } catch (err) {
      setRunning(false)
      notifyError(err instanceof ApiError ? err.message : 'Ошибка запуска')
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FlaskConical size={18} />
          Тесты (pytest)
        </CardTitle>
        <CardDescription>Запуск smoke-тестов backend из панели</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => handleRun()} disabled={running}>
            <Play size={16} />
            Запустить все ({tests.length})
          </Button>
          <Button variant="outline" onClick={load} disabled={loading || running}>
            <RefreshCw size={16} />
            Обновить список
          </Button>
        </div>
        {running && (
          <div className="space-y-2">
            <InlineProgressBar active={running} label={taskStatus || 'Выполнение тестов...'} />
          </div>
        )}
        {tests.length > 0 && (
          <ul className="max-h-48 space-y-1 overflow-y-auto rounded-md border p-3 text-sm">
            {tests.map((t) => (
              <li key={t.id} className="flex items-center justify-between gap-2">
                <span className="truncate">{t.title}</span>
                <Button size="sm" variant="ghost" disabled={running} onClick={() => handleRun([t.id])}>
                  Запуск
                </Button>
              </li>
            ))}
          </ul>
        )}
        {result && (
          <pre className="max-h-64 overflow-auto rounded-md border bg-muted/30 p-3 text-xs">{result}</pre>
        )}
      </CardContent>
    </Card>
  )
}
