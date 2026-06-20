import { FormEvent, useEffect, useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import Spinner from '@/components/ui/Spinner'
import {
  getTgTelegramSettings,
  testTgTelegram,
  updateTgTelegramSettings,
} from '@/tg-mini/api'
import {
  LABEL_AUTH_MAX_AGE,
  LABEL_BOT_USERNAME,
  LABEL_CHAT_ID,
} from '@/lib/uiLabels'
import type { TelegramSettings } from '@/types'

export default function TelegramSettings() {
  const [settings, setSettings] = useState<TelegramSettings | null>(null)
  const [botToken, setBotToken] = useState('')
  const [botUsername, setBotUsername] = useState('')
  const [authMaxAge, setAuthMaxAge] = useState('300')
  const [chatId, setChatId] = useState('')
  const [notifyEnabled, setNotifyEnabled] = useState(false)
  const [notifyOnBackup, setNotifyOnBackup] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getTgTelegramSettings()
      .then((data) => {
        setSettings(data)
        setBotUsername(data.bot_username)
        setAuthMaxAge(String(data.auth_max_age_seconds || 300))
        setChatId(data.chat_id)
        setNotifyEnabled(data.notify_enabled)
        setNotifyOnBackup(data.notify_on_backup)
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Ошибка загрузки'))
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setMessage(null)
    setError(null)
    try {
      const maxAge = Number.parseInt(authMaxAge, 10)
      const updated = await updateTgTelegramSettings({
        bot_token: botToken || undefined,
        bot_username: botUsername.trim() || undefined,
        auth_max_age_seconds: Number.isFinite(maxAge) ? maxAge : undefined,
        chat_id: chatId,
        notify_enabled: notifyEnabled,
        notify_on_backup: notifyOnBackup,
      })
      setSettings(updated)
      setBotToken('')
      setMessage('Настройки Telegram сохранены')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setMessage(null)
    try {
      const result = await testTgTelegram()
      setMessage(result.message)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка теста')
    } finally {
      setTesting(false)
    }
  }

  if (loading) {
    return (
      <div className="tg-mini-center py-4">
        <Spinner />
      </div>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Telegram (администратор)</CardTitle>
        <CardDescription>Настройки бота и уведомлений панели</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={(e) => void handleSave(e)}>
          <div className="space-y-2">
            <Label htmlFor="bot-token">Токен бота</Label>
            <Input
              id="bot-token"
              type="password"
              value={botToken}
              onChange={(e) => setBotToken(e.target.value)}
              placeholder={settings?.bot_token_set ? '••••••••' : 'Введите токен'}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="bot-username">{LABEL_BOT_USERNAME}</Label>
            <Input
              id="bot-username"
              value={botUsername}
              onChange={(e) => setBotUsername(e.target.value)}
              placeholder="@mybot"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="auth-max-age">{LABEL_AUTH_MAX_AGE}</Label>
            <Input
              id="auth-max-age"
              value={authMaxAge}
              onChange={(e) => setAuthMaxAge(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="chat-id">{LABEL_CHAT_ID}</Label>
            <Input id="chat-id" value={chatId} onChange={(e) => setChatId(e.target.value)} />
          </div>
          <label className="flex items-center justify-between gap-3 text-sm">
            <span>Уведомления включены</span>
            <input
              type="checkbox"
              checked={notifyEnabled}
              onChange={(e) => setNotifyEnabled(e.target.checked)}
            />
          </label>
          <label className="flex items-center justify-between gap-3 text-sm">
            <span>Уведомлять о бэкапах</span>
            <input
              type="checkbox"
              checked={notifyOnBackup}
              onChange={(e) => setNotifyOnBackup(e.target.checked)}
            />
          </label>
          {settings?.mini_app_url && (
            <p className="text-xs text-muted-foreground break-all">URL мини-приложения: {settings.mini_app_url}</p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={saving}>
              {saving ? 'Сохранение...' : 'Сохранить'}
            </Button>
            <Button type="button" variant="outline" disabled={testing} onClick={() => void handleTest()}>
              {testing ? 'Отправка...' : 'Тест бота'}
            </Button>
          </div>
        </form>
        {error && <p className="text-destructive text-sm mt-3">{error}</p>}
        {message && <p className="text-sm text-emerald-600 mt-3">{message}</p>}
      </CardContent>
    </Card>
  )
}
