import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '@/api/client'
import {
  getRequestsCooldown,
  releaseRequestsCooldown,
  updateRequestsCooldown,
  type CooldownBlockedItem,
  type CooldownSettings,
} from '@/api/users'
import AppDialog from '@/components/shared/AppDialog'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useNotifications } from '@/context/NotificationContext'

/** Настройка кулдауна после отказа и список тех, с кого его можно снять. */
export default function AccessCooldownDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { success, error: notifyError } = useNotifications()
  const [data, setData] = useState<CooldownSettings | null>(null)
  const [blocked, setBlocked] = useState<CooldownBlockedItem[]>([])
  const [total, setTotal] = useState(0)
  const [hours, setHours] = useState('24')
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [saving, setSaving] = useState(false)

  const PAGE = 50

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const next = await getRequestsCooldown({ limit: PAGE })
      setData(next)
      setBlocked(next.blocked)
      setTotal(next.total)
      setHours(String(next.hours))
    } catch {
      notifyError('Не удалось загрузить настройки кулдауна')
    } finally {
      setLoading(false)
    }
  }, [notifyError])

  const loadMore = async () => {
    if (loadingMore || blocked.length >= total) return
    setLoadingMore(true)
    try {
      const next = await getRequestsCooldown({ limit: PAGE, offset: blocked.length })
      setBlocked((prev) => [...prev, ...next.blocked])
      setTotal(next.total)
    } catch {
      notifyError('Не удалось догрузить список')
    } finally {
      setLoadingMore(false)
    }
  }

  useEffect(() => {
    if (open) void load()
  }, [open, load])

  const save = async () => {
    const value = Number.parseInt(hours, 10)
    if (!Number.isFinite(value) || value < 0 || value > 720) {
      notifyError('Кулдаун: целое число от 0 до 720 часов')
      return
    }
    setSaving(true)
    try {
      const next = await updateRequestsCooldown(value)
      setData(next)
      setBlocked(next.blocked)
      setTotal(next.total)
      success('Настройка кулдауна сохранена')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось сохранить кулдаун')
    } finally {
      setSaving(false)
    }
  }

  const release = async (telegramId: string) => {
    try {
      const result = await releaseRequestsCooldown(telegramId)
      success(result.message)
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось снять кулдаун')
    }
  }

  return (
    <AppDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Кулдаун отказов"
      description="Сколько часов после отказа нельзя подать заявку повторно и кто сейчас в кулдауне"
      size="lg"
    >
      {loading && !data ? (
        <Spinner label="Загрузка…" />
      ) : (
        <div className="space-y-4">
          <div className="flex flex-col gap-3 rounded-lg border bg-muted/20 p-4 sm:flex-row sm:items-end sm:justify-between">
            <div className="min-w-0">
              <p className="text-sm font-medium">Кулдаун после отказа</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                Сколько часов повторная заявка отклоняется. 0 — выключен.
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Input
                type="number"
                min={0}
                max={720}
                className="h-9 w-20"
                value={hours}
                onChange={(event) => setHours(event.target.value)}
                aria-label="Часы кулдауна"
              />
              <Button size="sm" onClick={() => void save()} disabled={saving}>
                {saving ? '…' : 'Сохранить'}
              </Button>
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium">Сейчас в кулдауне</p>
            {blocked.length > 0 ? (
              <div className="flex flex-col gap-1">
                {blocked.map((item) => (
                  <div
                    key={item.telegram_id}
                    className="flex flex-col gap-2 rounded-lg border border-border/60 px-3 py-2 text-sm sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0">
                      <p className="break-words font-medium">{item.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {item.request_type} · до {new Date(item.until).toLocaleString('ru-RU')}
                      </p>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void release(item.telegram_id)}
                    >
                      Снять
                    </Button>
                  </div>
                ))}
                {blocked.length < total && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="self-center"
                    onClick={() => void loadMore()}
                    disabled={loadingMore}
                  >
                    {loadingMore ? 'Загрузка…' : `Показать ещё (${total - blocked.length})`}
                  </Button>
                )}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Никого нет — повторную заявку никто не ждёт.
              </p>
            )}
            {total > 0 && (
              <p className="text-xs text-muted-foreground">
                Показаны {blocked.length} из {total}
              </p>
            )}
          </div>
        </div>
      )}
    </AppDialog>
  )
}
