import { FormEvent, useEffect, useState } from 'react'
import { Bell, Save } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError, getAdminNotifySettings, updateAdminNotifySettings } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { useNotifications } from '@/context/NotificationContext'
import { cn } from '@/lib/utils'

const GRACE_PRESETS = [1, 3, 5, 10] as const

export default function NodeOfflineNotifyCard() {
  const { success, error: notifyError } = useNotifications()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [enabled, setEnabled] = useState(true)
  const [graceMinutes, setGraceMinutes] = useState('3')
  const [notifyGlobalEnabled, setNotifyGlobalEnabled] = useState(false)
  const [botTokenSet, setBotTokenSet] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getAdminNotifySettings()
      .then((data) => {
        if (cancelled) return
        const event = data.events.find((item) => item.key === 'node_offline')
        setEnabled(event?.enabled ?? true)
        setGraceMinutes(String(Math.max(1, Math.round((data.node_offline_grace_seconds ?? 180) / 60))))
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

  const handleSave = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const minutes = Math.max(1, Math.min(1440, Number.parseInt(graceMinutes, 10) || 3))
      const updated = await updateAdminNotifySettings({
        events: { node_offline: enabled },
        node_offline_grace_seconds: minutes * 60,
      })
      const event = updated.events.find((item) => item.key === 'node_offline')
      setEnabled(event?.enabled ?? enabled)
      setGraceMinutes(String(Math.max(1, Math.round((updated.node_offline_grace_seconds ?? 180) / 60))))
      setNotifyGlobalEnabled(updated.notify_enabled)
      setBotTokenSet(updated.bot_token_set)
      success('Настройки уведомлений об offline сохранены')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="border-border/70">
      <CardContent className="p-4">
        {loading ? (
          <div className="flex justify-center py-4">
            <Spinner />
          </div>
        ) : (
          <form onSubmit={(e) => void handleSave(e)} className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2.5">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                  <Bell size={16} />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold tracking-tight">Telegram · offline</p>
                  <p className="text-xs text-muted-foreground">
                    Алерт после порога ·{' '}
                    <Link to="/telegram?tab=notify" className="underline underline-offset-2">
                      все уведомления
                    </Link>
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Вкл.</span>
                <Switch checked={enabled} onCheckedChange={setEnabled} aria-label="Уведомлять об offline" />
              </div>
            </div>

            {(!notifyGlobalEnabled || !botTokenSet) && (
              <SettingsAlert variant="warning" className="py-2.5">
                {!botTokenSet
                  ? 'Задайте токен бота в разделе Telegram.'
                  : 'Включите отправку уведомлений администратору в Telegram.'}
              </SettingsAlert>
            )}

            <div
              className={cn(
                'flex flex-wrap items-center gap-2',
                !enabled && 'pointer-events-none opacity-50',
              )}
            >
              <span className="text-xs text-muted-foreground">Порог</span>
              <Input
                id="nodesOfflineGraceMinutes"
                type="number"
                min={1}
                max={1440}
                className="h-8 w-16 tabular-nums"
                value={graceMinutes}
                onChange={(e) => setGraceMinutes(e.target.value)}
                disabled={!enabled}
                aria-label="Порог offline в минутах"
              />
              <span className="text-xs text-muted-foreground">мин</span>
              <div className="flex flex-wrap gap-1">
                {GRACE_PRESETS.map((mins) => (
                  <Button
                    key={mins}
                    type="button"
                    size="sm"
                    variant={graceMinutes === String(mins) ? 'secondary' : 'ghost'}
                    className="h-8 px-2.5 text-xs"
                    disabled={!enabled}
                    onClick={() => setGraceMinutes(String(mins))}
                  >
                    {mins}
                  </Button>
                ))}
              </div>
              <Button type="submit" size="sm" className="ml-auto h-8" disabled={saving || !enabled}>
                <Save size={14} />
                {saving ? '…' : 'Сохранить'}
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  )
}
