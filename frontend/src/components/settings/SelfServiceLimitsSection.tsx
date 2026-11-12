import { useEffect, useState } from 'react'
import { ApiError, getSelfServiceLimits, updateSelfServiceLimits } from '@/api/client'
import SelfServiceLimitsForm, {
  QUOTA_MAX,
  RATE_MAX,
  WINDOW_MAX_MINUTES,
  WINDOW_MIN_MINUTES,
  parseSelfServiceLimits,
  windowMinutesFromSeconds,
  type SelfServiceLimitsValues,
} from '@/components/shared/SelfServiceLimitsForm'
import Spinner from '@/components/ui/Spinner'
import { useNotifications } from '@/context/NotificationContext'
import type { SelfServiceLimits } from '@/types'

export default function SelfServiceLimitsSection() {
  const { success, error: notifyError } = useNotifications()
  const [loaded, setLoaded] = useState<SelfServiceLimits | null>(null)
  const [values, setValues] = useState<SelfServiceLimitsValues>({
    quota: '',
    rateMax: '',
    windowMinutes: '',
  })
  const [saving, setSaving] = useState(false)

  const apply = (data: SelfServiceLimits) => {
    setLoaded(data)
    setValues({
      quota: String(data.quota_default),
      rateMax: String(data.create_rate_max),
      windowMinutes: windowMinutesFromSeconds(data.create_rate_window_seconds),
    })
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
    const parsed = parseSelfServiceLimits(values)
    if (parsed.quota === null) {
      notifyError(`Квота: целое число от 0 до ${QUOTA_MAX}`)
      return
    }
    if (parsed.rateMax === null) {
      notifyError(`Созданий за окно: целое число от 0 до ${RATE_MAX}`)
      return
    }
    if (parsed.windowMinutes === null) {
      notifyError(`Окно: от ${WINDOW_MIN_MINUTES} до ${WINDOW_MAX_MINUTES} минут`)
      return
    }
    const payload: Partial<SelfServiceLimits> = {
      quota_default: parsed.quota,
      create_rate_max: parsed.rateMax,
    }
    if (
      values.windowMinutes.trim() !== windowMinutesFromSeconds(loaded.create_rate_window_seconds)
    ) {
      payload.create_rate_window_seconds = parsed.windowMinutes * 60
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
    <SelfServiceLimitsForm
      values={values}
      onChange={setValues}
      onSave={() => void save()}
      disabled={saving}
    />
  )
}
