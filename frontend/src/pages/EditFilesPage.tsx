import { useEffect, useState } from 'react'
import { FileText, Save } from 'lucide-react'
import { ApiError, getEditFileContent, getEditFiles, saveEditFile } from '@/api/client'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import Spinner from '@/components/ui/Spinner'
import { Textarea } from '@/components/ui/textarea'
import { useAuth } from '@/context/AuthContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import type { EditFileEntry } from '@/types'

export default function EditFilesPage() {
  const { user } = useAuth()
  const { success, error: notifyError } = useNotifications()
  const { startGlobal, doneGlobal, inline, withInline } = useProgress()
  const [files, setFiles] = useState<EditFileEntry[]>([])
  const [activeKey, setActiveKey] = useState<string | null>(null)
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (user?.role === 'viewer') return
    startGlobal()
    getEditFiles()
      .then((list) => {
        setFiles(list)
        if (list.length > 0) setActiveKey(list[0].key)
      })
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки'))
      .finally(() => {
        setLoading(false)
        doneGlobal()
      })
  }, [user?.role])

  useEffect(() => {
    if (!activeKey) return
    getEditFileContent(activeKey)
      .then((r) => setContent(r.content))
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка чтения файла'))
  }, [activeKey])

  const handleSave = async () => {
    if (!activeKey) return
    setSaving(true)
    try {
      await withInline(() => saveEditFile(activeKey, content), 'Сохранение и doall.sh...')
      success('Файл сохранён и применён')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  if (user?.role === 'viewer') {
    return <p className="text-muted-foreground">Редактирование файлов недоступно для роли viewer.</p>
  }

  if (loading) return <Spinner label="Загрузка файлов..." />

  const active = files.find((f) => f.key === activeKey)

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Редактор файлов</h2>
        <p className="text-sm text-muted-foreground">Все конфигурационные файлы AntiZapret (10 файлов)</p>
      </div>
      <InlineProgressBar active={inline.active} label={inline.label} />
      <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Файлы</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 p-2">
            {files.map((f) => (
              <button
                key={f.key}
                type="button"
                onClick={() => setActiveKey(f.key)}
                className={`w-full rounded-md px-3 py-2 text-left text-sm transition-colors ${
                  activeKey === f.key ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'
                }`}
              >
                <div className="font-medium">{f.title}</div>
                <div className="text-xs opacity-70">{f.filename}</div>
              </button>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FileText size={18} />
              {active?.title || 'Редактор'}
            </CardTitle>
            <CardDescription>{active?.filename}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className="min-h-[400px] font-mono text-xs"
              disabled={user?.role !== 'admin'}
            />
            {user?.role === 'admin' && (
              <Button onClick={handleSave} disabled={saving}>
                <Save size={16} />
                {saving ? 'Сохранение...' : 'Сохранить и применить'}
              </Button>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
