import { FormEvent, useEffect, useState } from 'react'
import { Bell, Send } from 'lucide-react'
import {
  ApiError,
  getAdminNotifySettings,
  getTelegramSettings,
  testAdminNotify,
  testTelegram,
  updateAdminNotifySettings,
  updateTelegramSettings,
} from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { useNotifications } from '@/context/NotificationContext'
import type { AdminNotifySettings, TelegramSettings } from '@/types'

export default function TelegramTab() {
  const { success, error: notifyError } = useNotifications()
  const [settings, setSettings] = useState<TelegramSettings | null>(null)
  const [adminNotify, setAdminNotify] = useState<AdminNotifySettings | null>(null)
  const [botToken, setBotToken] = useState('')
  const [chatId, setChatId] = useState('')
  const [telegramId, setTelegramId] = useState('')
  const [notifyEnabled, setNotifyEnabled] = useState(false)
  const [eventToggles, setEventToggles] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState(false)
  const [savingNotify, setSavingNotify] = useState(false)
  const [loading, setLoading] = useState(true)
  const [testing, setTesting] = useState(false)
  const [testingNotify, setTestingNotify] = useState(false)

  useEffect(() => {
    setLoading(true)
    Promise.all([getTelegramSettings(), getAdminNotifySettings()])
      .then(([tg, notify]) => {
        setSettings(tg)
        setChatId(tg.chat_id)
        setNotifyEnabled(tg.notify_enabled)
        setAdminNotify(notify)
        setTelegramId(notify.telegram_id)
        setEventToggles(Object.fromEntries(notify.events.map((e) => [e.key, e.enabled])))
      })
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки'))
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const updated = await updateTelegramSettings({
        bot_token: botToken || undefined,
        chat_id: chatId,
        notify_enabled: notifyEnabled,
      })
      setSettings(updated)
      setNotifyEnabled(updated.notify_enabled)
      setBotToken('')
      success('Настройки Telegram сохранены')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  const handleSaveAdminNotify = async (e: FormEvent) => {
    e.preventDefault()
    setSavingNotify(true)
    try {
      const updated = await updateAdminNotifySettings({
        telegram_id: telegramId,
        events: eventToggles,
      })
      setAdminNotify(updated)
      setTelegramId(updated.telegram_id)
      setEventToggles(Object.fromEntries(updated.events.map((item) => [item.key, item.enabled])))
      success('Настройки уведомлений сохранены')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSavingNotify(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    try {
      await testTelegram()
      success('Тестовое сообщение отправлено в chat_id')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка отправки')
    } finally {
      setTesting(false)
    }
  }

  const handleTestAdminNotify = async () => {
    setTestingNotify(true)
    try {
      await testAdminNotify()
      success('Тестовое уведомление отправлено на ваш Telegram ID')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка отправки')
    } finally {
      setTestingNotify(false)
    }
  }

  if (loading) {
    return <Spinner label="Загрузка настроек Telegram..." className="py-12" />
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Send size={18} />
            Бот и доставка бэкапов
          </CardTitle>
          <CardDescription>Токен бота и chat_id для бэкапов и тестового сообщения</CardDescription>
        </CardHeader>
        <CardContent>
          <InlineProgressBar active={saving || testing} label={testing ? 'Отправка сообщения...' : saving ? 'Сохранение настроек...' : undefined} />
          <form onSubmit={handleSave} className="grid max-w-lg gap-4">
            <div className="space-y-2">
              <Label htmlFor="botToken">Токен бота</Label>
              <Input
                id="botToken"
                type="password"
                value={botToken}
                onChange={(e) => setBotToken(e.target.value)}
                placeholder={settings?.bot_token_set ? '•••••••• (оставьте пустым, чтобы не менять)' : '123456:ABC...'}
              />
              <p className="text-xs text-muted-foreground">
                {settings?.bot_token_set ? 'Токен уже задан — введите новый только для замены' : 'Получите токен у @BotFather'}
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="chatId">Chat ID (бэкапы)</Label>
              <Input id="chatId" value={chatId} onChange={(e) => setChatId(e.target.value)} placeholder="-1001234567890" />
              <p className="text-xs text-muted-foreground">ID чата для доставки архивов бэкапов</p>
            </div>
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={notifyEnabled}
                onChange={(e) => setNotifyEnabled(e.target.checked)}
                className="h-4 w-4 rounded border"
              />
              Включить уведомления администратору (глобально)
            </label>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={saving}>
                {saving ? 'Сохранение...' : 'Сохранить'}
              </Button>
              <Button type="button" variant="secondary" onClick={handleTest} disabled={testing || !settings?.bot_token_set}>
                {testing ? 'Отправка...' : 'Тест в chat_id'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Bell size={18} />
            Уведомления администратору
          </CardTitle>
          <CardDescription>
            Per-user доставка на ваш Telegram ID. Требуются токен бота и включённый глобальный переключатель выше.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <InlineProgressBar
            active={savingNotify || testingNotify}
            label={testingNotify ? 'Отправка уведомления...' : savingNotify ? 'Сохранение подписок...' : undefined}
          />
          <form onSubmit={handleSaveAdminNotify} className="grid max-w-2xl gap-4">
            <div className="space-y-2">
              <Label htmlFor="telegramId">Ваш Telegram ID</Label>
              <Input
                id="telegramId"
                value={telegramId}
                onChange={(e) => setTelegramId(e.target.value)}
                placeholder="123456789"
              />
              <p className="text-xs text-muted-foreground">
                Узнайте ID у @userinfobot или при входе через Telegram
              </p>
            </div>
            <div className="space-y-3">
              <Label>Типы событий</Label>
              <div className="grid gap-2 sm:grid-cols-2">
                {adminNotify?.events.map((event) => (
                  <label key={event.key} className="flex cursor-pointer items-start gap-2 rounded-md border p-3 text-sm">
                    <input
                      type="checkbox"
                      checked={eventToggles[event.key] ?? false}
                      onChange={(e) =>
                        setEventToggles((prev) => ({ ...prev, [event.key]: e.target.checked }))
                      }
                      className="mt-0.5 h-4 w-4 shrink-0 rounded border"
                    />
                    <span>{event.label}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={savingNotify}>
                {savingNotify ? 'Сохранение...' : 'Сохранить подписки'}
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={handleTestAdminNotify}
                disabled={testingNotify || !adminNotify?.bot_token_set || !telegramId}
              >
                {testingNotify ? 'Отправка...' : 'Тест моих уведомлений'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
