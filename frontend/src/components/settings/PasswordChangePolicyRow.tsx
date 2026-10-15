import { useEffect, useState } from 'react'
import { ApiError, getSelfServiceLimits, updateSelfServiceLimits } from '@/api/client'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useNotifications } from '@/context/NotificationContext'

export default function PasswordChangePolicyRow() {
  const { success, error: notifyError } = useNotifications()
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    getSelfServiceLimits()
      .then((data) => {
        if (!cancelled) setEnabled(data.require_password_change)
      })
      .catch((err) => {
        if (!cancelled) notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить настройку')
      })
    return () => {
      cancelled = true
    }
  }, [notifyError])

  const toggle = async (next: boolean) => {
    setSaving(true)
    try {
      const data = await updateSelfServiceLimits({ require_password_change: next })
      setEnabled(data.require_password_change)
      success(next ? 'Смена пароля при первом входе включена' : 'Смена пароля при первом входе выключена')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось сохранить настройку')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex items-start justify-between gap-4 rounded-xl border bg-card/50 p-4">
      <div className="min-w-0 space-y-1">
        <Label htmlFor="requirePasswordChange" className="cursor-pointer font-medium">
          Требовать смену пароля при первом входе
        </Label>
        <p className="text-xs leading-relaxed text-muted-foreground">
          Для новых учётных записей и после сброса пароля администратором. До смены пароля панель недоступна,
          Mini App работает.
        </p>
      </div>
      <Switch
        id="requirePasswordChange"
        checked={enabled ?? false}
        disabled={enabled === null || saving}
        onCheckedChange={(next) => void toggle(next)}
      />
    </div>
  )
}
