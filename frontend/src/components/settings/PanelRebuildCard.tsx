import { useState } from 'react'
import { Hammer, Rocket, Server } from 'lucide-react'
import { ApiError, rebuildPanel } from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import {
  SettingsCard as Card,
  SettingsCardContent as CardContent,
  SettingsCardDescription as CardDescription,
  SettingsCardHeader as CardHeader,
  SettingsCardTitle as CardTitle,
} from '@/components/settings/SettingsCard'
import { SettingsDangerZone } from '@/components/settings/SettingsChrome'
import {
  UPDATE_CONFIRM_DURATION_NOTICE,
  UPDATE_LONG_RUNNING_NOTICE,
  UPDATE_POLL_BUSY_ALERT_BODY,
  UPDATE_POLL_BUSY_ALERT_TITLE,
  isLikelyBuildBusyPollError,
  resolveUpdateTaskErrorMessage,
} from '@/components/settings/updateGuidance'
import { Button } from '@/components/ui/button'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'

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
    <div className={className}>
      <ConfirmDialogHost dialogProps={dialogProps} />
      <Card>
        <CardHeader>
          <div className="flex items-start gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Rocket size={16} aria-hidden />
            </span>
            <div className="min-w-0">
              <CardTitle>Пересборка интерфейса</CardTitle>
              <CardDescription className="mt-1">
                Полная сборка frontend и mini-app без обновления кода из Git — как{' '}
                <code className="rounded bg-muted px-1 py-0.5 text-[11px]">
                  {'npm run build:all && systemctl restart adminpanelaz'}
                </code>
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2 sm:grid-cols-2">
            {REBUILD_STEPS.map((step) => (
              <div
                key={step.label}
                className="flex items-start gap-3 rounded-lg border bg-muted/15 p-3 text-sm"
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <step.icon size={16} aria-hidden />
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
          <SettingsDangerZone
            title="Пересобрать и перезапустить"
            description="После сборки сервис перезапустится — дождитесь завершения процесса, не запускайте обновление параллельно."
          >
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
          </SettingsDangerZone>
        </CardContent>
      </Card>
    </div>
  )
}
