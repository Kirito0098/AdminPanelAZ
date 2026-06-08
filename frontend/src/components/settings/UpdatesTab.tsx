import { useEffect, useState } from 'react'
import { Download, RefreshCw } from 'lucide-react'
import { ApiError, applySystemUpdate, checkSystemUpdates } from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import Spinner from '@/components/ui/Spinner'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { useProgress } from '@/context/ProgressContext'

export default function UpdatesTab() {
  const { success, error: notifyError } = useNotifications()
  const { inline, trackBackgroundTask, backgroundTaskPolling } = useProgress()
  const { confirm, dialogProps } = useConfirmDialog()
  const [info, setInfo] = useState<{
    updates_available?: boolean
    commits_behind?: number
    local_hash?: string
    remote_hash?: string
    error?: string
  } | null>(null)
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      setInfo(await checkSystemUpdates())
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка проверки обновлений')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleUpdate = () => {
    confirm({
      title: 'Применить обновление?',
      description: 'Будет выполнен git pull origin main. Панель может потребовать перезапуска.',
      alert: {
        variant: 'warning',
        title: 'Перед обновлением',
        children: 'Рекомендуется создать бэкап. После git pull может потребоваться перезапуск панели и применение миграций.',
      },
      confirmLabel: 'Применить обновление',
      destructive: true,
      onConfirm: async () => {
        setUpdating(true)
        try {
          const resp = await applySystemUpdate()
          trackBackgroundTask(resp.task_id, {
            onComplete: () => {
              success(resp.message || 'Обновление применено')
              void load()
            },
            onError: (task, message) => {
              notifyError(task?.error || task?.message || message)
            },
          })
        } catch (err) {
          notifyError(err instanceof ApiError ? err.message : 'Ошибка обновления')
        } finally {
          setUpdating(false)
        }
      },
    })
  }

  if (loading && !info) {
    return <Spinner label="Проверка обновлений..." className="py-12" />
  }

  return (
    <div className="space-y-4">
      <ConfirmDialogHost dialogProps={dialogProps} />
      <InlineProgressBar active={inline.active || updating || backgroundTaskPolling} label={inline.label || (updating ? 'Применение обновления...' : undefined)} />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Download size={18} />
            Системные обновления
          </CardTitle>
          <CardDescription>Git fetch + pull из origin/main</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" onClick={load} disabled={loading || updating}>
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
              Проверить
            </Button>
            {info?.updates_available ? (
              <Badge variant="destructive">{info.commits_behind} коммит(ов) позади</Badge>
            ) : (
              <Badge variant="secondary">Актуально</Badge>
            )}
          </div>
          {info && (
            <div className="grid gap-3 rounded-md border bg-muted/30 p-4 text-sm md:grid-cols-2">
              <div>
                <span className="text-muted-foreground">Локальный: </span>
                <code className="font-mono text-xs">{info.local_hash || '—'}</code>
              </div>
              <div>
                <span className="text-muted-foreground">Удалённый: </span>
                <code className="font-mono text-xs">{info.remote_hash || '—'}</code>
              </div>
            </div>
          )}
          {info?.error && (
            <SettingsAlert variant="danger" title="Ошибка проверки">
              {info.error}
            </SettingsAlert>
          )}
        </CardContent>
      </Card>

      {info?.updates_available && (
        <Card className="border-destructive/20">
          <CardHeader>
            <CardTitle className="text-base text-destructive">Применить обновление</CardTitle>
            <CardDescription>Загрузит и применит изменения из удалённого репозитория</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <SettingsAlert variant="warning" title="Перед обновлением">
              Рекомендуется создать бэкап. После git pull может потребоваться перезапуск панели и применение миграций.
            </SettingsAlert>
            <Button variant="destructive" onClick={handleUpdate} disabled={updating}>
              {updating ? 'Обновление...' : 'Применить обновление'}
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
