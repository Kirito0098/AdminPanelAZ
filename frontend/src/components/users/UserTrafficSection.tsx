import { lazy, Suspense, useState } from 'react'
import { Gauge, RotateCcw } from 'lucide-react'
import { ApiError } from '@/api/client'
import { resetUserTrafficCounter, setUserTrafficLimit } from '@/api/users'
import AppDialog from '@/components/shared/AppDialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PercentBar } from '@/components/ui/percent-bar'
import Spinner from '@/components/ui/Spinner'
import UserSection from './UserSection'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import { formatDate } from '@/lib/datetime'
import { formatBytes } from '@/lib/trafficFormat'
import { cn } from '@/lib/utils'
import type { UserProvisioningCard } from '@/types'

// Графики тянут recharts: держим их в отдельном чанке и грузим только на вкладке «Трафик».
const UserStatsSection = lazy(() => import('./UserStatsSection'))

const GIGABYTE = 1024 ** 3

interface UserTrafficSectionProps {
  card: UserProvisioningCard
  onRefresh: () => void
}

/** Лимит трафика абонента и графики расхода по дням. */
export default function UserTrafficSection({ card, onRefresh }: UserTrafficSectionProps) {
  const { user } = card
  const { isEnabled } = useFeatureModules()
  const { success, error: notifyError } = useNotifications()
  const [busy, setBusy] = useState(false)
  const [limitOpen, setLimitOpen] = useState(false)
  const [limitGb, setLimitGb] = useState('')

  const trafficSyncOn = isEnabled('traffic_sync')
  const limitBytes = user.traffic_limit_bytes ?? null
  const consumedBytes = user.traffic_consumed_bytes ?? 0
  const percent = limitBytes ? Math.min((consumedBytes / limitBytes) * 100, 100) : 0

  const run = async (action: () => Promise<void>, message: string) => {
    setBusy(true)
    try {
      await action()
      success(message)
      onRefresh()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка выполнения операции')
    } finally {
      setBusy(false)
    }
  }

  const openLimit = () => {
    setLimitGb(limitBytes != null ? String(Math.round((limitBytes / GIGABYTE) * 100) / 100) : '')
    setLimitOpen(true)
  }

  const handleSave = () => {
    const gb = Number.parseFloat(limitGb.replace(',', '.'))
    if (!Number.isFinite(gb) || gb <= 0) {
      notifyError('Укажите лимит трафика в ГБ (например, 100)')
      return
    }
    setLimitOpen(false)
    void run(async () => {
      await setUserTrafficLimit(user.id, Math.round(gb * GIGABYTE))
    }, 'Лимит трафика сохранён')
  }

  const handleClear = () => {
    void run(async () => {
      await setUserTrafficLimit(user.id, null)
    }, 'Ограничение трафика снято')
  }

  const handleResetCounter = () => {
    void run(async () => {
      await resetUserTrafficCounter(user.id)
    }, 'Счётчик трафика сброшен')
  }

  return (
    <div className="space-y-4">
      <UserSection
        icon={Gauge}
        title="Лимит трафика"
        description="Общий лимит на все конфиги. По умолчанию без ограничений."
        actions={
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={openLimit}
            disabled={busy || !trafficSyncOn}
          >
            {limitBytes == null ? 'Задать лимит' : 'Изменить лимит'}
          </Button>
        }
      >
        <div className="space-y-3">
          {!trafficSyncOn && (
            <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
              Модуль «Синхронизация трафика» выключен — лимит не работает. Включите его в
              Настройках → Модули.
            </p>
          )}
          {limitBytes == null ? (
            <p className="text-sm text-muted-foreground">Без ограничений.</p>
          ) : (
            <>
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <p className="text-2xl font-semibold leading-none">{formatBytes(consumedBytes)}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    из {formatBytes(limitBytes)}
                    {user.traffic_counter_reset_at
                      ? ` · счётчик с ${formatDate(user.traffic_counter_reset_at)}`
                      : ''}
                  </p>
                </div>
                <span
                  className={cn(
                    'text-sm font-semibold',
                    user.traffic_limit_blocked ? 'text-destructive' : 'text-muted-foreground',
                  )}
                >
                  {Math.round(percent)}%
                </span>
              </div>
              <PercentBar
                value={consumedBytes}
                max={limitBytes}
                className="h-2"
                barClassName={
                  user.traffic_limit_blocked
                    ? 'fill-destructive'
                    : percent >= 80
                      ? 'fill-amber-500'
                      : 'fill-primary'
                }
                label="Использование лимита трафика"
              />
              {user.traffic_limit_blocked && (
                <p className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  Лимит исчерпан — доступ заблокирован.
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={handleResetCounter}
                  disabled={busy || !trafficSyncOn}
                >
                  <RotateCcw size={15} />
                  Сбросить счётчик
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={handleClear} disabled={busy}>
                  Снять ограничение
                </Button>
              </div>
            </>
          )}
        </div>
      </UserSection>

      <Suspense fallback={<Spinner label="Загрузка графиков…" className="py-8" />}>
        <UserStatsSection userId={user.id} />
      </Suspense>

      <AppDialog
        open={limitOpen}
        onOpenChange={setLimitOpen}
        title="Лимит трафика"
        description="Укажите лимит в гигабайтах. Счётчик отсчитывается с момента установки лимита."
        icon={Gauge}
        size="sm"
        footer={
          <>
            <Button
              type="button"
              variant="outline"
              onClick={() => setLimitOpen(false)}
              disabled={busy}
            >
              Отмена
            </Button>
            <Button type="button" onClick={handleSave} disabled={busy}>
              Сохранить
            </Button>
          </>
        }
      >
        <div className="space-y-1.5">
          <Label htmlFor="trafficLimitGb">Лимит, ГБ</Label>
          <Input
            id="trafficLimitGb"
            value={limitGb}
            onChange={(e) => setLimitGb(e.target.value)}
            inputMode="decimal"
            placeholder="100"
          />
        </div>
      </AppDialog>
    </div>
  )
}
