import { useState } from 'react'
import { RefreshCw, ServerCrash } from 'lucide-react'
import { ApiError, restartPanel } from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { useNotifications } from '@/context/NotificationContext'
import { cn } from '@/lib/utils'

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
      description: 'Сервис adminpanelaz будет перезапущен через systemd или start.sh.',
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
    <div className={cn('md:col-span-2', className)}>
      <ConfirmDialogHost dialogProps={dialogProps} />
      <Card className="overflow-hidden border-destructive/30 shadow-sm">
        <div className="h-1 bg-gradient-to-r from-destructive/80 to-destructive/20" />
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <ServerCrash size={18} className="text-destructive" />
            Перезапуск панели
          </CardTitle>
          <CardDescription>
            Применяет изменения из .env и перезапускает сервис adminpanelaz без обновления кода
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <SettingsAlert variant="warning" title="Кратковременная недоступность">
            Панель будет недоступна несколько секунд. Незавершённые фоновые задачи прервутся.
          </SettingsAlert>
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
        </CardContent>
      </Card>
    </div>
  )
}
