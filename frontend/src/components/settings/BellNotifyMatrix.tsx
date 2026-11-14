import { useCallback, useEffect, useState } from 'react'
import { Bell, RefreshCw } from 'lucide-react'
import {
  SettingsCard as Card,
  SettingsCardContent as CardContent,
  SettingsCardDescription as CardDescription,
  SettingsCardHeader as CardHeader,
  SettingsCardTitle as CardTitle,
} from '@/components/settings/SettingsCard'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { CATEGORY_ICON, CATEGORY_LABEL } from '@/components/notifications/labels'
import {
  fetchBellNotifyAdmins,
  saveBellNotifyAdmin,
  type BellNotifyAdmin,
  type NotificationCategory,
} from '@/api/notifications'

const CATEGORIES: NotificationCategory[] = ['requests', 'security', 'nodes', 'services', 'tasks']

const GRID_COLS = 'grid-cols-[minmax(7rem,1.2fr)_repeat(5,minmax(5.5rem,1fr))]'

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

  const renderSwitch = (admin: BellNotifyAdmin, key: NotificationCategory) => (
    <Switch
      checked={admin.categories[key]}
      disabled={savingId !== null}
      onCheckedChange={(checked) => void toggle(admin, key, checked)}
      aria-label={`${admin.username}: ${CATEGORY_LABEL[key]}`}
    />
  )

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Bell size={18} aria-hidden />
            </span>
            <div className="min-w-0">
              <CardTitle>Матрица подписок</CardTitle>
              <CardDescription className="mt-1">
                Кто из админов видит категорию в колокольчике и ленте «Уведомления». На Telegram не
                влияет.
              </CardDescription>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5 text-muted-foreground"
            onClick={() => void load()}
            disabled={loading || savingId !== null}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : undefined} />
            Обновить
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {error && <p className="mb-3 text-xs text-destructive">{error}</p>}
        {loading ? (
          <p className="py-6 text-sm text-muted-foreground">Загрузка…</p>
        ) : admins.length === 0 ? (
          <p className="py-6 text-sm text-muted-foreground">Админов нет.</p>
        ) : (
          <>
            <div className="hidden overflow-hidden rounded-lg border border-border/70 md:block">
              <div
                className={`grid ${GRID_COLS} items-center gap-2 border-b border-border/70 bg-muted/30 px-3 py-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground`}
              >
                <span>Админ</span>
                {CATEGORIES.map((key) => {
                  const Icon = CATEGORY_ICON[key]
                  return (
                    <span
                      key={key}
                      className="flex items-center justify-center gap-1.5 text-center leading-tight"
                    >
                      <Icon size={12} className="shrink-0" />
                      {CATEGORY_LABEL[key]}
                    </span>
                  )
                })}
              </div>
              {admins.map((admin) => (
                <div
                  key={admin.user_id}
                  className={`grid ${GRID_COLS} items-center gap-2 border-b border-border/40 px-3 py-2.5 transition-colors last:border-0 hover:bg-muted/30`}
                >
                  <span className="truncate text-sm font-medium">{admin.username}</span>
                  {CATEGORIES.map((key) => (
                    <div key={key} className="flex justify-center">
                      {renderSwitch(admin, key)}
                    </div>
                  ))}
                </div>
              ))}
            </div>

            <div className="flex flex-col gap-2.5 md:hidden">
              {admins.map((admin) => (
                <div
                  key={admin.user_id}
                  className="rounded-lg border border-border/70 bg-card/40 p-3"
                >
                  <p className="mb-2 text-sm font-medium">{admin.username}</p>
                  <div className="flex flex-col gap-2">
                    {CATEGORIES.map((key) => {
                      const Icon = CATEGORY_ICON[key]
                      return (
                        <label
                          key={key}
                          className="flex items-center justify-between gap-3 rounded-lg border border-border/50 px-2.5 py-1.5 text-xs"
                        >
                          <span className="flex items-center gap-1.5 text-muted-foreground">
                            <Icon size={12} className="shrink-0" />
                            {CATEGORY_LABEL[key]}
                          </span>
                          {renderSwitch(admin, key)}
                        </label>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
