import { useEffect, useState } from 'react'
import { Save } from 'lucide-react'
import { ApiError, updateTelegramRelay } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useNotifications } from '@/context/NotificationContext'
import { formatDateTime } from '@/lib/datetime'
import type { TelegramSettings } from '@/types'

const DIRECT = 'direct'

interface TelegramRelayCardProps {
  settings: TelegramSettings
  onSaved: (updated: TelegramSettings) => void
}

function relayStatus(settings: TelegramSettings): string {
  if (!settings.interactive_enabled) return 'Опрос начнётся, когда включите ответы на команды'
  if (settings.relay_last_ok_at) return `Последний опрос: ${formatDateTime(settings.relay_last_ok_at)}`
  return 'Ждём первый опрос — обычно до минуты'
}

export default function TelegramRelayCard({ settings, onSaved }: TelegramRelayCardProps) {
  const { success, error: notifyError } = useNotifications()
  const current = settings.relay_node_id ? String(settings.relay_node_id) : DIRECT
  const [choice, setChoice] = useState(current)
  const [saving, setSaving] = useState(false)

  useEffect(() => setChoice(current), [current])

  const save = async () => {
    setSaving(true)
    try {
      const updated = await updateTelegramRelay(choice === DIRECT ? null : Number(choice))
      onSaved(updated)
      success(choice === DIRECT ? 'Бот снова работает напрямую — подключите его к панели' : 'Telegram подключён через узел')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось сохранить')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-3 border-t pt-4">
      <div>
        <Label htmlFor="telegramRelay">Связь с Telegram</Label>
        <p className="mt-1 text-xs text-muted-foreground">
          Если сервер панели в РФ и бот молчит, пустите запросы к Telegram через зарубежный VPN-узел. Панель сама
          забирает сообщения, входящий доступ из интернета не нужен.
        </p>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <Select value={choice} onValueChange={setChoice} disabled={saving}>
          <SelectTrigger id="telegramRelay" className="sm:max-w-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={DIRECT}>Напрямую (webhook)</SelectItem>
            {settings.relay_nodes.map((node) => (
              <SelectItem key={node.id} value={String(node.id)}>
                Через узел {node.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void save()}
          disabled={saving || choice === current}
        >
          <Save size={15} />
          {saving ? 'Проверяем связь...' : 'Сохранить'}
        </Button>
      </div>
      {settings.relay_nodes.length === 0 && (
        <p className="text-xs text-muted-foreground">
          Подходящих узлов нет: нужен удалённый VPN-узел с mTLS или SSH-транспортом и агентом 1.13.0 или новее.
        </p>
      )}
      {settings.relay_node_id ? (
        settings.relay_last_error ? (
          <SettingsAlert variant="danger" title="Узел не достучался до Telegram">
            {settings.relay_last_error}
          </SettingsAlert>
        ) : (
          <p className="text-xs text-muted-foreground">{relayStatus(settings)}</p>
        )
      ) : null}
    </div>
  )
}
