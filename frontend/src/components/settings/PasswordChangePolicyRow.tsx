import { useEffect, useState } from 'react'
import { ApiError, getSelfServiceLimits, updateSelfServiceLimits } from '@/api/client'
import ToggleRow from '@/components/settings/ToggleRow'
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
    <ToggleRow
      id="requirePasswordChange"
      label="Требовать смену пароля при первом входе"
      description="Для новых учётных записей и после сброса пароля администратором. До смены пароля панель недоступна, Mini App работает."
      checked={enabled ?? false}
      disabled={enabled === null || saving}
      onCheckedChange={(next) => void toggle(next)}
    />
  )
}
