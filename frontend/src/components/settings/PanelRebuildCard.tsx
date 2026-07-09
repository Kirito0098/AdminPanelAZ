import { useState } from 'react'
import { Hammer, Rocket, Server } from 'lucide-react'
import { ApiError, rebuildPanel } from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import {
  UPDATE_CONFIRM_DURATION_NOTICE,
  UPDATE_LONG_RUNNING_NOTICE,
  UPDATE_POLL_BUSY_ALERT_BODY,
  UPDATE_POLL_BUSY_ALERT_TITLE,
  isLikelyBuildBusyPollError,
  resolveUpdateTaskErrorMessage,
} from '@/components/settings/updateGuidance'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { cn } from '@/lib/utils'

const REBUILD_STEPS = [
  { icon: Hammer, label: 'Сборка UI', detail: 'npm run build:all в frontend/' },
  { icon: Server, label: 'Перезапуск', detail: 'adminpanelaz через systemd' },
] as const

type Props = {
  className?: string
}

export default function PanelRebuildCard({ className }: Props) {
  const { success, error: notifyError, warning: notifyWarning } = useNotifications()
  const { trackBackgroundTask } = useProgress()
  const { confirm, dialogProps } = useConfirmDialog()
  const [rebuilding, setRebuilding] = useState(false)

  const handleRebuild = () => {
    confirm({
      title: 'Пересобрать интерфейс и перезапустить?',
      description: 'Выполнит npm run build:all и перезапустит сервис панели.',
      alert: {
        variant: 'warning',
        title: 'Займёт продолжительное время',
        children: (
          <>
            Панель будет недоступна после завершения сборки. Не запускайте одновременно с обновлением из Git.
            <br />
            <br />
            {UPDATE_CONFIRM_DURATION_NOTICE}
          </>
        ),
      },
      confirmLabel: 'Пересобрать и перезапустить',
      destructive: true,
      onConfirm: async () => {
        setRebuilding(true)
        try {
          const resp = await rebuildPanel()
          trackBackgroundTask(resp.task_id, {
            onComplete: () => {
              success(resp.message || 'Пересборка завершена, панель перезапускается')
            },
            onError: (task, message) => {
              const resolved = resolveUpdateTaskErrorMessage(message, task)
              if (isLikelyBuildBusyPollError(message, task)) {
                notifyWarning(resolved)
                return
              }
              notifyError(resolved)
            },
          })
        } catch (err) {
          notifyError(err instanceof ApiError ? err.message : 'Ошибка пересборки')
        } finally {
          setRebuilding(false)
        }
      },
    })
  }

  return (
    <div className={cn('md:col-span-2', className)}>
      <ConfirmDialogHost dialogProps={dialogProps} />
      <Card className="overflow-hidden border-amber-500/30 shadow-sm">
        <div className="h-1 bg-gradient-to-r from-amber-500/80 to-amber-500/20" />
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Rocket size={18} className="text-amber-600 dark:text-amber-400" />
            Пересборка интерфейса
          </CardTitle>
          <CardDescription>
            Полная сборка frontend и mini-app без обновления кода из Git — как{' '}
            <code className="text-xs">npm run build:all && systemctl restart adminpanelaz</code>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2 sm:grid-cols-2">
            {REBUILD_STEPS.map((step) => (
              <div
                key={step.label}
                className="flex items-start gap-3 rounded-xl border bg-card/60 p-3 text-sm"
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400">
                  <step.icon size={16} />
                </div>
                <div>
                  <p className="font-medium">{step.label}</p>
                  <p className="text-xs text-muted-foreground">{step.detail}</p>
                </div>
              </div>
            ))}
          </div>
          <SettingsAlert variant="info" title="Длительность пересборки">
            {UPDATE_LONG_RUNNING_NOTICE}
          </SettingsAlert>
          <SettingsAlert variant="info" title={UPDATE_POLL_BUSY_ALERT_TITLE}>
            {UPDATE_POLL_BUSY_ALERT_BODY}
          </SettingsAlert>
          <SettingsAlert variant="info" title="Когда использовать">
            После ручного изменения файлов frontend на сервере или если UI не обновился после деплоя.
          </SettingsAlert>
          <Button
            type="button"
            variant="destructive"
            className="gap-2"
            disabled={rebuilding}
            onClick={handleRebuild}
          >
            <Hammer size={16} />
            {rebuilding ? 'Запуск...' : 'Пересобрать и перезапустить'}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
