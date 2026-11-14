import { useEffect, useState } from 'react'
import { Bell, ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError, getAdminNotifySettings } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useNotifications } from '@/context/NotificationContext'

export default function NodeOfflineNotifyCard() {
  const { error: notifyError } = useNotifications()
  const [loading, setLoading] = useState(true)
  const [eventEnabled, setEventEnabled] = useState(false)
  const [graceMinutes, setGraceMinutes] = useState(3)
  const [notifyGlobalEnabled, setNotifyGlobalEnabled] = useState(false)
  const [botTokenSet, setBotTokenSet] = useState(false)

  useEffect(() => {
    let cancelled = false
    getAdminNotifySettings()
      .then((data) => {
        if (cancelled) return
        setEventEnabled(data.events.find((item) => item.key === 'node_offline')?.enabled ?? false)
        setGraceMinutes(Math.max(1, Math.round((data.node_offline_grace_seconds ?? 180) / 60)))
        setNotifyGlobalEnabled(data.notify_enabled)
        setBotTokenSet(data.bot_token_set)
      })
      .catch((err) => {
        if (!cancelled) {
          notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить настройки уведомлений')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [notifyError])

  const active = eventEnabled && notifyGlobalEnabled && botTokenSet

  return (
    <Card className="border-border/70">
      <CardContent className="p-4">
        {loading ? (
          <div className="flex justify-center py-4">
            <Spinner />
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2.5">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                  <Bell size={16} />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold tracking-tight">Telegram · offline</p>
                  <p className="text-xs text-muted-foreground">
                    Алерт после порога {graceMinutes} мин · настраивается в Настройках → Уведомления
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                <Badge variant={active ? 'success' : 'secondary'}>
                  {active ? 'Включены' : 'Выключены'}
                </Badge>
                <Button variant="outline" size="sm" asChild>
                  <Link to="/settings/notifications">
                    Настроить
                    <ChevronRight size={14} aria-hidden />
                  </Link>
                </Button>
              </div>
            </div>

            {!botTokenSet && (
              <SettingsAlert variant="warning" className="py-2.5">
                Задайте токен бота в разделе Telegram.
              </SettingsAlert>
            )}
            {botTokenSet && !notifyGlobalEnabled && (
              <SettingsAlert variant="warning" className="py-2.5">
                Включите отправку уведомлений администратору в Telegram.
              </SettingsAlert>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
