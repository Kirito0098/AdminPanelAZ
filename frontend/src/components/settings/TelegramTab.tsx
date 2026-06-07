import { FormEvent, useEffect, useState } from 'react'
import { Send } from 'lucide-react'
import { ApiError, getTelegramSettings, testTelegram, updateTelegramSettings } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useNotifications } from '@/context/NotificationContext'
import type { TelegramSettings } from '@/types'

export default function TelegramTab() {
  const { success, error: notifyError } = useNotifications()
  const [settings, setSettings] = useState<TelegramSettings | null>(null)
  const [botToken, setBotToken] = useState('')
  const [chatId, setChatId] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getTelegramSettings()
      .then((s) => {
        setSettings(s)
        setChatId(s.chat_id)
      })
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки'))
  }, [])

  const handleSave = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const updated = await updateTelegramSettings({
        bot_token: botToken || undefined,
        chat_id: chatId,
        notify_enabled: settings?.notify_enabled,
      })
      setSettings(updated)
      setBotToken('')
      success('Настройки Telegram сохранены')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    try {
      await testTelegram()
      success('Тестовое сообщение отправлено')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка отправки')
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Send size={18} />
          Telegram-уведомления
        </CardTitle>
        <CardDescription>Бот для оповещений администратора и доставки бэкапов</CardDescription>
      </CardHeader>
      <CardContent>
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
          </div>
          <div className="space-y-2">
            <Label htmlFor="chatId">Chat ID</Label>
            <Input id="chatId" value={chatId} onChange={(e) => setChatId(e.target.value)} placeholder="-1001234567890" />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={saving}>
              {saving ? 'Сохранение...' : 'Сохранить'}
            </Button>
            <Button type="button" variant="secondary" onClick={handleTest}>
              Тестовое сообщение
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}
