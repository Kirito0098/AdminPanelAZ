import { useEffect, useState } from 'react'
import { Save } from 'lucide-react'
import { ApiError, getSelfServiceLimits, updateSelfServiceLimits } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useNotifications } from '@/context/NotificationContext'
import { parseBoundedInt } from '@/lib/boundedInt'
import type { SelfServiceLimits } from '@/types'

const QUOTA_MAX = 1000
const RATE_MAX = 100
const WINDOW_MIN_MINUTES = 1
const WINDOW_MAX_MINUTES = 1440

function windowMinutes(seconds: number): string {
  return String(Math.max(WINDOW_MIN_MINUTES, Math.round(seconds / 60)))
}

export default function SelfServiceLimitsSection() {
  const { success, error: notifyError } = useNotifications()
  const [loaded, setLoaded] = useState<SelfServiceLimits | null>(null)
  const [quota, setQuota] = useState('')
  const [rateMax, setRateMax] = useState('')
  const [minutes, setMinutes] = useState('')
  const [saving, setSaving] = useState(false)

  const apply = (data: SelfServiceLimits) => {
    setLoaded(data)
    setQuota(String(data.quota_default))
    setRateMax(String(data.create_rate_max))
    setMinutes(windowMinutes(data.create_rate_window_seconds))
  }

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const data = await getSelfServiceLimits()
        if (!cancelled) apply(data)
      } catch (err) {
        if (!cancelled) notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить лимиты')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [notifyError])

  const save = async () => {
    if (!loaded) return
    const quotaValue = parseBoundedInt(quota, 0, QUOTA_MAX)
    const rateValue = parseBoundedInt(rateMax, 0, RATE_MAX)
    const minutesValue = parseBoundedInt(minutes, WINDOW_MIN_MINUTES, WINDOW_MAX_MINUTES)
    if (quotaValue === null) {
      notifyError(`Квота: целое число от 0 до ${QUOTA_MAX}`)
      return
    }
    if (rateValue === null) {
      notifyError(`Созданий за окно: целое число от 0 до ${RATE_MAX}`)
      return
    }
    if (minutesValue === null) {
      notifyError(`Окно: от ${WINDOW_MIN_MINUTES} до ${WINDOW_MAX_MINUTES} минут`)
      return
    }
    const payload: Partial<SelfServiceLimits> = {
      quota_default: quotaValue,
      create_rate_max: rateValue,
    }
    if (minutes.trim() !== windowMinutes(loaded.create_rate_window_seconds)) {
      payload.create_rate_window_seconds = minutesValue * 60
    }
    setSaving(true)
    try {
      apply(await updateSelfServiceLimits(payload))
      success('Лимиты сохранены')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения лимитов')
    } finally {
      setSaving(false)
    }
  }

  if (!loaded) return <Spinner label="Загрузка лимитов..." className="py-4" />

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label htmlFor="limitQuotaDefault">Квота конфигов по умолчанию</Label>
          <Input
            id="limitQuotaDefault"
            type="number"
            inputMode="numeric"
            min={0}
            max={QUOTA_MAX}
            value={quota}
            onChange={(e) => setQuota(e.target.value)}
            disabled={saving}
          />
          <p className="text-xs text-muted-foreground">
            Для пользователей без своей квоты. 0 — без лимита.
          </p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="limitCreateRateMax">Созданий за окно</Label>
          <Input
            id="limitCreateRateMax"
            type="number"
            inputMode="numeric"
            min={0}
            max={RATE_MAX}
            value={rateMax}
            onChange={(e) => setRateMax(e.target.value)}
            disabled={saving}
          />
          <p className="text-xs text-muted-foreground">
            Сколько конфигов пользователь создаст подряд. 0 — без ограничения.
          </p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="limitCreateRateWindow">Окно, минут</Label>
          <Input
            id="limitCreateRateWindow"
            type="number"
            inputMode="numeric"
            min={WINDOW_MIN_MINUTES}
            max={WINDOW_MAX_MINUTES}
            value={minutes}
            onChange={(e) => setMinutes(e.target.value)}
            disabled={saving}
          />
          <p className="text-xs text-muted-foreground">
            От {WINDOW_MIN_MINUTES} до {WINDOW_MAX_MINUTES} (сутки).
          </p>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        Счётчик созданий хранится в памяти панели и обнуляется при её перезапуске. На администраторов лимиты не
        действуют.
      </p>
      <Button type="button" size="sm" onClick={() => void save()} disabled={saving}>
        <Save size={15} />
        {saving ? 'Сохранение...' : 'Сохранить лимиты'}
      </Button>
    </div>
  )
}
