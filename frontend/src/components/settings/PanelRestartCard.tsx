import { useState } from 'react'
import { RefreshCw, ServerCrash } from 'lucide-react'
import { ApiError, restartPanel } from '@/api/client'
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
import { Button } from '@/components/ui/button'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { useNotifications } from '@/context/NotificationContext'

type Props = {
  className?: string
  compact?: boolean
  onRestartScheduled?: () => void
}

export default function PanelRestartCard({ className, compact = false, onRestartScheduled }: Props) {
  const { success, error: notifyError } = useNotifications()
  const { confirm, dialogProps } = useConfirmDialog()
  const [restarting, setRestarting] = useState(false)

  const handleRestart = () => {
    confirm({
      title: 'Перезапустить панель?',
      description: 'Сервис adminpanelaz будет перезапущен через systemd.',
      alert: {
        variant: 'warning',
        title: 'Сессия прервётся',
        children:
          'Страница станет недоступна на несколько секунд. Активные фоновые задачи будут прерваны.',
      },
      confirmLabel: 'Перезапустить панель',
      destructive: true,
      onConfirm: async () => {
        setRestarting(true)
        try {
          const resp = await restartPanel()
          success(resp.message || 'Перезапуск панели запланирован')
          onRestartScheduled?.()
        } catch (err) {
          notifyError(err instanceof ApiError ? err.message : 'Ошибка перезапуска панели')
        } finally {
          setRestarting(false)
        }
      },
    })
  }

  if (compact) {
    return (
      <>
        <ConfirmDialogHost dialogProps={dialogProps} />
        <Button type="button" size="sm" variant="destructive" disabled={restarting} onClick={handleRestart}>
          <RefreshCw size={14} className={restarting ? 'animate-spin' : ''} />
          {restarting ? 'Перезапуск...' : 'Перезапустить панель'}
        </Button>
      </>
    )
  }

  return (
    <div className={className}>
      <ConfirmDialogHost dialogProps={dialogProps} />
      <Card>
        <CardHeader>
          <div className="flex items-start gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
              <ServerCrash size={16} aria-hidden />
            </span>
            <div className="min-w-0">
              <CardTitle>Перезапуск панели</CardTitle>
              <CardDescription className="mt-1">
                Применяет изменения из .env и перезапускает сервис adminpanelaz без обновления кода
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <SettingsAlert variant="warning" title="Кратковременная недоступность">
            Панель будет недоступна несколько секунд. Незавершённые фоновые задачи прервутся.
          </SettingsAlert>
          <SettingsDangerZone
            title="Перезапустить сервис"
            description="Сессия прервётся, страница станет недоступна на несколько секунд."
          >
            <Button
              type="button"
              variant="destructive"
              className="gap-2"
              disabled={restarting}
              onClick={handleRestart}
            >
              <RefreshCw size={16} className={restarting ? 'animate-spin' : ''} />
              {restarting ? 'Перезапуск...' : 'Перезапустить панель'}
            </Button>
          </SettingsDangerZone>
        </CardContent>
      </Card>
    </div>
  )
}
