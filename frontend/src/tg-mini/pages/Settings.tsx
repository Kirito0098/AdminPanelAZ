import { FormEvent, useEffect, useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import Spinner from '@/components/ui/Spinner'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'
import TelegramSettings from '@/tg-mini/pages/TelegramSettings'
import { getTgAdminNotify, testTgAdminNotify, updateTgAdminNotify } from '@/tg-mini/api'
import { LABEL_TELEGRAM_ID } from '@/lib/uiLabels'
import type { AdminNotifySettings } from '@/types'

export default function Settings() {
  const { settings, isAdmin } = useTgAuth()
  const [notify, setNotify] = useState<AdminNotifySettings | null>(null)
  const [telegramId, setTelegramId] = useState('')
  const [eventToggles, setEventToggles] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    getTgAdminNotify()
      .then((data) => {
        setNotify(data)
        setTelegramId(data.telegram_id)
        setEventToggles(Object.fromEntries(data.events.map((event) => [event.key, event.enabled])))
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Ошибка загрузки'))
      .finally(() => setLoading(false))
  }, [])

  const handleSaveNotify = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setMessage(null)
    try {
      const updated = await updateTgAdminNotify({
        events: eventToggles,
      })
      setNotify(updated)
      setMessage('Настройки уведомлений сохранены')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  const handleTestNotify = async () => {
    setTesting(true)
    setMessage(null)
    try {
      const result = await testTgAdminNotify()
      setMessage(result.message)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка теста')
    } finally {
      setTesting(false)
    }
  }

  if (loading) {
    return (
      <div className="tg-mini-center">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Аккаунт</CardTitle>
          <CardDescription>Информация о текущем пользователе</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>
            <span className="text-muted-foreground">Пользователь:</span> {settings?.username}
          </p>
          <p>
            <span className="text-muted-foreground">Роль:</span> {settings?.role}
          </p>
          <p>
            <span className="text-muted-foreground">Сервер:</span> {settings?.server_ip || '—'}
          </p>
          <p>
            <span className="text-muted-foreground">Бот:</span>{' '}
            {settings?.bot_configured ? 'настроен' : 'не настроен'}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Уведомления</CardTitle>
          <CardDescription>Личные Telegram-уведомления</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={(e) => void handleSaveNotify(e)}>
            <div className="space-y-2">
              <Label htmlFor="telegram-id">{LABEL_TELEGRAM_ID}</Label>
              <p id="telegram-id" className="text-sm font-mono">
                {telegramId || '—'}
              </p>
              <p className="text-xs text-muted-foreground">
                Привязка через /link в боте или в веб-панели (Настройки → Пользователи).
              </p>
            </div>
            {notify?.events.map((event) => (
              <label key={event.key} className="flex items-center justify-between gap-3 text-sm">
                <span>{event.label}</span>
                <input
                  type="checkbox"
                  checked={Boolean(eventToggles[event.key])}
                  onChange={(e) =>
                    setEventToggles((prev) => ({ ...prev, [event.key]: e.target.checked }))
                  }
                />
              </label>
            ))}
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={saving}>
                {saving ? 'Сохранение...' : 'Сохранить'}
              </Button>
              <Button type="button" variant="outline" disabled={testing} onClick={() => void handleTestNotify()}>
                {testing ? 'Отправка...' : 'Тест'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {isAdmin && <TelegramSettings />}

      {error && <p className="text-destructive text-sm">{error}</p>}
      {message && <p className="text-sm text-emerald-600">{message}</p>}
    </div>
  )
}
