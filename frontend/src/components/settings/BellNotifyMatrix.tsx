import { useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Bell } from 'lucide-react'
import { CATEGORY_LABEL } from '@/components/notifications/labels'
import {
  fetchBellNotifyAdmins,
  saveBellNotifyAdmin,
  type BellNotifyAdmin,
  type NotificationCategory,
} from '@/api/notifications'

const CATEGORIES: NotificationCategory[] = ['requests', 'security', 'nodes', 'services', 'tasks']

export default function BellNotifyMatrix() {
  const [admins, setAdmins] = useState<BellNotifyAdmin[]>([])
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState<number | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setAdmins(await fetchBellNotifyAdmins())
    } catch {
      setError('Не удалось загрузить подписки админов')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const toggle = async (admin: BellNotifyAdmin, key: NotificationCategory, value: boolean) => {
    if (savingId !== null) return
    const previous = admin.categories
    const next = { ...previous, [key]: value }
    setSavingId(admin.user_id)
    setError('')
    setAdmins((prev) =>
      prev.map((item) => (item.user_id === admin.user_id ? { ...item, categories: next } : item)),
    )
    try {
      const saved = await saveBellNotifyAdmin(admin.user_id, next)
      setAdmins((prev) => prev.map((item) => (item.user_id === saved.user_id ? saved : item)))
    } catch {
      setAdmins((prev) =>
        prev.map((item) =>
          item.user_id === admin.user_id ? { ...item, categories: previous } : item,
        ),
      )
      setError(`Не удалось сохранить: ${admin.username}`)
    } finally {
      setSavingId(null)
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Bell size={18} />
              Уведомления в панели
            </CardTitle>
            <CardDescription className="mt-1.5">
              Какие категории каждый админ видит в колокольчике и ленте «Уведомления». На Telegram
              не влияет — там своя настройка выше.
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading || savingId !== null}>
            Обновить
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <p className="text-sm text-muted-foreground">Загрузка…</p>
        ) : admins.length === 0 ? (
          <p className="text-sm text-muted-foreground">Админов нет.</p>
        ) : (
          <div className="flex flex-col gap-3">
            {admins.map((admin) => (
              <div
                key={admin.user_id}
                className="flex flex-col gap-2 rounded-xl border border-border/60 px-3 py-2.5 lg:flex-row lg:items-center lg:justify-between"
              >
                <span className="text-sm font-medium">{admin.username}</span>
                <div className="flex flex-wrap gap-x-4 gap-y-2">
                  {CATEGORIES.map((key) => (
                    <label key={key} className="flex items-center gap-2 text-xs">
                      <Switch
                        checked={admin.categories[key]}
                        disabled={savingId !== null}
                        onCheckedChange={(checked) => void toggle(admin, key, checked)}
                        aria-label={`${admin.username}: ${CATEGORY_LABEL[key]}`}
                      />
                      {CATEGORY_LABEL[key]}
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
        {error && <p className="mt-3 text-xs text-destructive">{error}</p>}
      </CardContent>
    </Card>
  )
}
