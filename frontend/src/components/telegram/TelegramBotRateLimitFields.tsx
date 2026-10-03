import { useEffect, useState } from 'react'
import { Save } from 'lucide-react'
import { ApiError, updateTelegramSettings } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useNotifications } from '@/context/NotificationContext'
import { parseBoundedInt } from '@/lib/boundedInt'
import type { TelegramSettings } from '@/types'

const MAX_COMMANDS = 1000
const WINDOW_MIN = 10
const WINDOW_MAX = 3600

interface TelegramBotRateLimitFieldsProps {
  settings: TelegramSettings
  onSaved: (updated: TelegramSettings) => void
}

export default function TelegramBotRateLimitFields({ settings, onSaved }: TelegramBotRateLimitFieldsProps) {
  const { success, error: notifyError } = useNotifications()
  const [maxCommands, setMaxCommands] = useState(String(settings.bot_command_rate_max))
  const [windowSeconds, setWindowSeconds] = useState(String(settings.bot_command_rate_window_seconds))
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setMaxCommands(String(settings.bot_command_rate_max))
    setWindowSeconds(String(settings.bot_command_rate_window_seconds))
  }, [settings.bot_command_rate_max, settings.bot_command_rate_window_seconds])

  const save = async () => {
    const maxValue = parseBoundedInt(maxCommands, 0, MAX_COMMANDS)
    const windowValue = parseBoundedInt(windowSeconds, WINDOW_MIN, WINDOW_MAX)
    if (maxValue === null) {
      notifyError(`Команд за окно: целое число от 0 до ${MAX_COMMANDS}`)
      return
    }
    if (windowValue === null) {
      notifyError(`Окно: от ${WINDOW_MIN} до ${WINDOW_MAX} секунд`)
      return
    }
    setSaving(true)
    try {
      const updated = await updateTelegramSettings({
        bot_command_rate_max: maxValue,
        bot_command_rate_window_seconds: windowValue,
      })
      onSaved(updated)
      success('Лимит команд сохранён')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-3 border-t pt-4">
      <div>
        <Label>Лимит команд</Label>
        <p className="mt-1 text-xs text-muted-foreground">
          Сколько команд один привязанный пользователь может отправить боту за окно. 0 — без ограничения. Счётчик
          хранится в памяти панели и обнуляется при её перезапуске.
        </p>
      </div>
      {!settings.bot_command_rate_limit_enabled && (
        <SettingsAlert variant="warning" title="Лимит выключен на сервере">
          В <code>.env</code> задано <code>TELEGRAM_BOT_COMMAND_RATE_LIMIT_ENABLED=false</code> — значения ниже
          сохранятся, но применяться не будут.
        </SettingsAlert>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="botCommandRateMax">Команд за окно</Label>
          <Input
            id="botCommandRateMax"
            type="number"
            inputMode="numeric"
            min={0}
            max={MAX_COMMANDS}
            value={maxCommands}
            onChange={(e) => setMaxCommands(e.target.value)}
            disabled={saving}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="botCommandRateWindow">Окно, секунд</Label>
          <Input
            id="botCommandRateWindow"
            type="number"
            inputMode="numeric"
            min={WINDOW_MIN}
            max={WINDOW_MAX}
            value={windowSeconds}
            onChange={(e) => setWindowSeconds(e.target.value)}
            disabled={saving}
          />
        </div>
      </div>
      <Button type="button" size="sm" variant="outline" onClick={() => void save()} disabled={saving}>
        <Save size={15} />
        {saving ? 'Сохранение...' : 'Сохранить лимит'}
      </Button>
    </div>
  )
}
