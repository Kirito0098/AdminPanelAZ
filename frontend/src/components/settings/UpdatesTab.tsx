import { useEffect, useState } from 'react'
import { Download, RefreshCw } from 'lucide-react'
import { ApiError, applySystemUpdate, checkSystemUpdates, getLatestChangelog } from '@/api/client'
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
import type { LatestChangelog } from '@/types'

export default function UpdatesTab() {
  const { success, error: notifyError } = useNotifications()
  const { trackBackgroundTask } = useProgress()
  const { confirm, dialogProps } = useConfirmDialog()
  const [info, setInfo] = useState<{
    updates_available?: boolean
    commits_behind?: number
    local_hash?: string
    remote_hash?: string
    error?: string
  } | null>(null)
  const [changelog, setChangelog] = useState<LatestChangelog | null>(null)
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const updates = await checkSystemUpdates()
      setInfo(updates)
      if (updates.updates_available) {
        try {
          setChangelog(await getLatestChangelog())
        } catch {
          setChangelog(null)
        }
      } else {
        setChangelog(null)
      }
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
      description: 'Будет выполнен git pull, обновление pip/npm, сборка frontend и перезапуск панели.',
      alert: {
        variant: 'warning',
        title: 'Перед обновлением',
        children: 'Рекомендуется создать бэкап. Панель перезапустится автоматически через несколько секунд после сборки.',
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
      <InlineProgressBar active={updating} label="Применение обновления..." />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Download size={18} />
            Системные обновления
          </CardTitle>
          <CardDescription>Git pull, pip/npm, сборка frontend и перезапуск панели</CardDescription>
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
            {changelog?.success && changelog.version && (
              <div className="rounded-lg border bg-muted/30 p-4 text-sm">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="rounded-md bg-primary/10 px-2 py-0.5 font-mono text-xs font-semibold text-primary">
                    v{changelog.version}
                  </span>
                  <span className="text-muted-foreground">{changelog.date}</span>
                </div>
                <div className="mt-4 max-h-96 space-y-4 overflow-y-auto pr-1">
                  {(changelog.sections ?? []).map((section) => (
                    <div key={section.title}>
                      <p className="font-medium">{section.title}</p>
                      <ul className="mt-1.5 space-y-1 pl-4">
                        {section.items.map((item) => (
                          <li key={item} className="list-disc text-muted-foreground marker:text-muted-foreground/60">
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <SettingsAlert variant="warning" title="Перед обновлением">
              Рекомендуется создать бэкап. После применения панель перезапустится автоматически (systemd или start.sh).
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
