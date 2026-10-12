import { useEffect, useState, type FormEvent } from 'react'
import { Loader2 } from 'lucide-react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { parseBoundedInt } from '@/lib/boundedInt'
import { getTgSelfServiceLimits, updateTgSelfServiceLimits, updateTgTelegramSettings } from '@/tg-mini/api'
import type { SelfServiceLimits, TelegramSettings } from '@/types'

type Feedback = { tone: 'success' | 'error' | 'info'; text: string }

interface MiniLimitsFormProps {
  telegram: TelegramSettings
  onTelegramSaved: (updated: TelegramSettings) => void
  onFeedback: (feedback: Feedback) => void
}

interface FieldSpec {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  min: number
  max: number
}

function LimitField({ id, label, value, onChange, min, max, disabled }: FieldSpec & { disabled: boolean }) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        className="h-11"
        type="number"
        inputMode="numeric"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      />
    </div>
  )
}

export default function MiniLimitsForm({ telegram, onTelegramSaved, onFeedback }: MiniLimitsFormProps) {
  const [limits, setLimits] = useState<SelfServiceLimits | null>(null)
  const [quota, setQuota] = useState('')
  const [rateMax, setRateMax] = useState('')
  const [rateMinutes, setRateMinutes] = useState('')
  const [botMax, setBotMax] = useState(String(telegram.bot_command_rate_max))
  const [botWindow, setBotWindow] = useState(String(telegram.bot_command_rate_window_seconds))
  const [saving, setSaving] = useState(false)

  const applyLimits = (data: SelfServiceLimits) => {
    setLimits(data)
    setQuota(String(data.quota_default))
    setRateMax(String(data.create_rate_max))
    setRateMinutes(String(Math.max(1, Math.round(data.create_rate_window_seconds / 60))))
  }

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const data = await getTgSelfServiceLimits()
        if (!cancelled) applyLimits(data)
      } catch (err) {
        if (!cancelled) {
          onFeedback({ tone: 'error', text: err instanceof ApiError ? err.message : 'Не удалось загрузить лимиты' })
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [onFeedback])

  useEffect(() => {
    setBotMax(String(telegram.bot_command_rate_max))
    setBotWindow(String(telegram.bot_command_rate_window_seconds))
  }, [telegram.bot_command_rate_max, telegram.bot_command_rate_window_seconds])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!limits) return
    const values = {
      quota: parseBoundedInt(quota, 0, 1000),
      rateMax: parseBoundedInt(rateMax, 0, 100),
      rateMinutes: parseBoundedInt(rateMinutes, 1, 1440),
      botMax: parseBoundedInt(botMax, 0, 1000),
      botWindow: parseBoundedInt(botWindow, 10, 3600),
    }
    if (Object.values(values).some((v) => v === null)) {
      onFeedback({
        tone: 'error',
        text: 'Проверьте значения: квота 0–1000, созданий 0–100, окно 1–1440 мин, команд 0–1000, окно бота 10–3600 с',
      })
      return
    }
    const selfServicePayload: Partial<SelfServiceLimits> = {
      quota_default: values.quota as number,
      create_rate_max: values.rateMax as number,
    }
    if (rateMinutes.trim() !== String(Math.max(1, Math.round(limits.create_rate_window_seconds / 60)))) {
      selfServicePayload.create_rate_window_seconds = (values.rateMinutes as number) * 60
    }
    setSaving(true)
    try {
      const [updatedLimits, updatedTelegram] = await Promise.all([
        updateTgSelfServiceLimits(selfServicePayload),
        updateTgTelegramSettings({
          bot_command_rate_max: values.botMax as number,
          bot_command_rate_window_seconds: values.botWindow as number,
        }),
      ])
      applyLimits(updatedLimits)
      onTelegramSaved(updatedTelegram)
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
      onFeedback({ tone: 'success', text: 'Лимиты сохранены' })
    } catch (err) {
      onFeedback({ tone: 'error', text: err instanceof ApiError ? err.message : 'Ошибка сохранения лимитов' })
    } finally {
      setSaving(false)
    }
  }

  if (!limits) {
    return (
      <div className="tg-mini-center py-2">
        <Loader2 size={18} className="animate-spin text-muted-foreground" aria-label="Загрузка лимитов" />
      </div>
    )
  }

  const selfServiceFields: FieldSpec[] = [
    { id: 'limit-quota', label: 'Квота по умолчанию', value: quota, onChange: setQuota, min: 0, max: 1000 },
    { id: 'limit-rate-max', label: 'Созданий за окно', value: rateMax, onChange: setRateMax, min: 0, max: 100 },
    { id: 'limit-rate-window', label: 'Окно создания, мин', value: rateMinutes, onChange: setRateMinutes, min: 1, max: 1440 },
  ]
  const botFields: FieldSpec[] = [
    { id: 'limit-bot-max', label: 'Команд бота за окно', value: botMax, onChange: setBotMax, min: 0, max: 1000 },
    { id: 'limit-bot-window', label: 'Окно бота, сек', value: botWindow, onChange: setBotWindow, min: 10, max: 3600 },
  ]

  return (
    <form className="space-y-4" onSubmit={(e) => void handleSubmit(e)}>
      <div className="space-y-3">
        <div className="grid grid-cols-1 gap-3 min-[380px]:grid-cols-3">
          {selfServiceFields.map((field) => (
            <LimitField key={field.id} {...field} disabled={saving} />
          ))}
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">
          Создание конфигов обычными пользователями. 0 — без лимита.
        </p>
      </div>
      <div className="space-y-3">
        <div className="grid grid-cols-1 gap-3 min-[380px]:grid-cols-2">
          {botFields.map((field) => (
            <LimitField key={field.id} {...field} disabled={saving} />
          ))}
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">
          {telegram.bot_command_rate_limit_enabled
            ? 'Команды одного пользователя боту. 0 — без ограничения.'
            : 'Лимит команд выключен в .env (TELEGRAM_BOT_COMMAND_RATE_LIMIT_ENABLED=false) — значения не применяются.'}
        </p>
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">
        Счётчики хранятся в памяти панели и обнуляются при перезапуске.
      </p>
      <Button type="submit" className="gap-1.5" disabled={saving}>
        {saving ? <Loader2 size={16} className="animate-spin" aria-hidden /> : null}
        Сохранить лимиты
      </Button>
    </form>
  )
}
