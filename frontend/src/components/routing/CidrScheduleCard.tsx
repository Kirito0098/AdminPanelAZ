import { useEffect, useMemo, useState } from 'react'
import { CalendarClock, Save } from 'lucide-react'
import { ApiError, getCidrDbSchedule, updateCidrDbSchedule } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useNotifications } from '@/context/NotificationContext'
import { formatDateTime } from '@/lib/datetime'
import { cn } from '@/lib/utils'
import type { CidrDbSchedule } from '@/types'

const INTERVAL_PRESETS = [1, 3, 7, 14] as const

function intervalLabel(days: number): string {
  if (days === 1) return 'каждую ночь'
  if (days === 7) return 'раз в неделю'
  if (days === 14) return 'раз в 2 недели'
  return `каждые ${days} дн.`
}

export default function CidrScheduleCard() {
  const { success, error: notifyError } = useNotifications()
  const [schedule, setSchedule] = useState<CidrDbSchedule | null>(null)
  const [draft, setDraft] = useState<CidrDbSchedule | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      setLoading(true)
      try {
        const data = await getCidrDbSchedule()
        if (cancelled) return
        setSchedule(data)
        setDraft(data)
      } catch (err) {
        if (!cancelled) {
          notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить расписание CIDR')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once on mount
  }, [])

  const dirty = useMemo(() => {
    if (!schedule || !draft) return false
    return (
      schedule.enabled !== draft.enabled ||
      schedule.refresh_time !== draft.refresh_time ||
      schedule.interval_days !== draft.interval_days
    )
  }, [schedule, draft])

  const patchDraft = (patch: Partial<CidrDbSchedule>) => {
    setDraft((prev) => (prev ? { ...prev, ...patch } : prev))
  }

  const save = async () => {
    if (!draft) return
    setSaving(true)
    try {
      const updated = await updateCidrDbSchedule({
        enabled: draft.enabled,
        refresh_time: draft.refresh_time,
        interval_days: draft.interval_days,
      })
      setSchedule(updated)
      setDraft(updated)
      success('Расписание автообновления CIDR сохранено')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось сохранить расписание')
    } finally {
      setSaving(false)
    }
  }

  if (loading && !draft) {
    return (
      <Card className="overflow-hidden shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <CalendarClock size={18} />
            Автообновление CIDR
          </CardTitle>
          <CardDescription>Загрузка расписания…</CardDescription>
        </CardHeader>
      </Card>
    )
  }

  if (!draft) return null

  return (
    <Card className="overflow-hidden shadow-sm">
      <div className="h-1 bg-gradient-to-r from-cyan-500/70 to-cyan-500/15" />
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <CalendarClock size={18} />
          Автообновление CIDR
        </CardTitle>
        <CardDescription>
          Когда и как часто панель сама загружает базу провайдеров. Время — UTC.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div
          className={cn(
            'flex items-start justify-between gap-4 rounded-xl border bg-card/50 p-4 transition-colors',
            draft.enabled && 'border-primary/20 bg-primary/5',
          )}
        >
          <div className="min-w-0 space-y-1">
            <Label htmlFor="cidr-auto-refresh" className="cursor-pointer font-medium">
              Включить автообновление
            </Label>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Фоновая загрузка из интернета в SQLite на контроллере (этап 1)
            </p>
          </div>
          <Switch
            id="cidr-auto-refresh"
            checked={draft.enabled}
            onCheckedChange={(checked) => patchDraft({ enabled: checked })}
          />
        </div>

        {draft.enabled && (
          <div className="grid gap-4 rounded-xl border bg-muted/20 p-4 md:grid-cols-2">
            <div className="space-y-3">
              <Label htmlFor="cidr-refresh-time" className="text-xs text-muted-foreground">
                Время запуска (UTC)
              </Label>
              <Input
                id="cidr-refresh-time"
                type="time"
                className="h-9 w-36"
                value={draft.refresh_time}
                onChange={(e) => patchDraft({ refresh_time: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">
                Сейчас: {intervalLabel(draft.interval_days)} в {draft.refresh_time} UTC
              </p>
            </div>

            <div className="space-y-3">
              <Label className="text-xs text-muted-foreground">Интервал, дней</Label>
              <div className="flex flex-wrap gap-2">
                {INTERVAL_PRESETS.map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => patchDraft({ interval_days: d })}
                    className={cn(
                      'rounded-lg border px-3 py-1.5 text-sm font-medium transition-all',
                      draft.interval_days === d
                        ? 'border-primary bg-primary/10 text-primary ring-1 ring-primary'
                        : 'hover:border-muted-foreground/30 hover:bg-muted/50',
                    )}
                  >
                    {d} дн.
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-2">
                <Input
                  id="cidr-interval-days"
                  type="number"
                  min={1}
                  max={90}
                  className="h-9 w-20"
                  value={draft.interval_days}
                  onChange={(e) =>
                    patchDraft({ interval_days: Math.max(1, Math.min(90, Number(e.target.value) || 1)) })
                  }
                />
                <span className="text-xs text-muted-foreground">дней между запусками</span>
              </div>
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4 text-xs text-muted-foreground">
          <div className="space-y-0.5">
            <p>
              Последний автозапуск:{' '}
              <span className="text-foreground">
                {schedule?.last_run_at ? formatDateTime(schedule.last_run_at) : 'ещё не было'}
              </span>
            </p>
            {draft.enabled && schedule?.next_run_at && (
              <p>
                Следующая проверка:{' '}
                <span className="text-foreground">{formatDateTime(schedule.next_run_at)}</span>
              </p>
            )}
          </div>
          <Button
            disabled={!dirty || saving}
            onClick={() => void save()}
            className="gap-1.5"
          >
            <Save size={16} />
            {saving ? 'Сохранение…' : 'Сохранить'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
