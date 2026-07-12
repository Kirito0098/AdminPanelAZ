import { FormEvent, useEffect, useState } from 'react'
import { Bell, Save } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError, getAdminNotifySettings, updateAdminNotifySettings } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import Spinner from '@/components/ui/Spinner'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useNotifications } from '@/context/NotificationContext'

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
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Bell size={18} />
          Telegram: узел offline
        </CardTitle>
        <CardDescription>
          Алерт придёт только после непрерывного offline дольше порога. То же значение — во вкладке{' '}
          <Link to="/telegram?tab=notify" className="underline underline-offset-2">
            Telegram → Уведомления
          </Link>
          .
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex justify-center py-6">
            <Spinner />
          </div>
        ) : (
          <form onSubmit={(e) => void handleSave(e)} className="space-y-4">
            <InlineProgressBar active={saving} label={saving ? 'Сохранение...' : undefined} />
            {(!notifyGlobalEnabled || !botTokenSet) && (
              <SettingsAlert variant="warning" title="Telegram-уведомления не готовы">
                {!botTokenSet
                  ? 'Задайте токен бота в разделе Telegram.'
                  : 'Включите «Отправлять уведомления администратору» в Telegram → Уведомления.'}
              </SettingsAlert>
            )}
            <div className="flex items-start justify-between gap-3 rounded-lg border p-3">
              <div className="space-y-1">
                <p className="text-sm font-medium">Уведомлять об offline / восстановлении</p>
                <p className="text-xs text-muted-foreground">
                  Событие AdminNotify «Узел offline / восстановление»
                </p>
              </div>
              <Switch checked={enabled} onCheckedChange={setEnabled} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="nodesOfflineGraceMinutes">Порог offline (мин)</Label>
              <div className="flex flex-wrap items-center gap-2">
                <Input
                  id="nodesOfflineGraceMinutes"
                  type="number"
                  min={1}
                  max={1440}
                  className="w-24"
                  value={graceMinutes}
                  onChange={(e) => setGraceMinutes(e.target.value)}
                  disabled={!enabled}
                />
                {GRACE_PRESETS.map((mins) => (
                  <Button
                    key={mins}
                    type="button"
                    size="sm"
                    variant={graceMinutes === String(mins) ? 'default' : 'outline'}
                    disabled={!enabled}
                    onClick={() => setGraceMinutes(String(mins))}
                  >
                    {mins} мин
                  </Button>
                ))}
              </div>
            </div>
            <Button type="submit" disabled={saving}>
              <Save size={16} />
              Сохранить
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  )
}
