import { useEffect, useState } from 'react'
import { Save } from 'lucide-react'
import { ApiError, getUserGraceSettings, updateUserGraceSettings } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { useNotifications } from '@/context/NotificationContext'
import type { UserGraceSettings } from '@/types'

const FALLBACK_MONTHS = [0, 1, 2, 3, 6, 12]

/** Срок удержания конфигов после истечения доступа (grace). */
export default function UserGraceSection() {
  const { success, error: notifyError } = useNotifications()
  const [loaded, setLoaded] = useState<UserGraceSettings | null>(null)
  const [months, setMonths] = useState(0)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const data = await getUserGraceSettings()
        if (cancelled) return
        setLoaded(data)
        setMonths(data.grace_months)
      } catch (err) {
        if (!cancelled) {
          notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить срок удержания')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [notifyError])

  const save = async () => {
    setSaving(true)
    try {
      const data = await updateUserGraceSettings(months)
      setLoaded(data)
      setMonths(data.grace_months)
      success('Срок удержания сохранён')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения срока удержания')
    } finally {
      setSaving(false)
    }
  }

  if (!loaded) return <Spinner label="Загрузка срока удержания..." className="py-4" />

  const options = loaded.allowed_months?.length ? loaded.allowed_months : FALLBACK_MONTHS

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="userGraceMonths">Удержание конфигов после истечения доступа</Label>
        <select
          id="userGraceMonths"
          value={String(months)}
          onChange={(e) => setMonths(Number.parseInt(e.target.value, 10))}
          disabled={saving}
          className="flex h-9 w-full max-w-xs rounded-md border border-input bg-background px-3 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
        >
          {options.map((value) => (
            <option key={value} value={String(value)}>
              {value === 0 ? 'Выключено (0 мес.)' : `${value} мес.`}
            </option>
          ))}
        </select>
        <p className="text-xs text-muted-foreground">
          После истечения срока доступа конфиги не удаляются автоматически — администратор получит
          одно предупреждение в «Задачах» и сможет удалить их вручную. 0 — предупреждений нет.
        </p>
      </div>
      <Button type="button" size="sm" onClick={() => void save()} disabled={saving}>
        <Save size={15} />
        {saving ? 'Сохранение...' : 'Сохранить'}
      </Button>
    </div>
  )
}
