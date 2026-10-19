import { useState } from 'react'
import { CalendarPlus, Gauge, PauseCircle, PlayCircle, RotateCcw } from 'lucide-react'
import { ApiError } from '@/api/client'
import {
  extendUserAccess,
  resetUserTrafficCounter,
  resumeUser,
  setUserTrafficLimit,
  suspendUser,
} from '@/api/users'
import AppDialog from '@/components/shared/AppDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import { formatDate } from '@/lib/datetime'
import { formatBytes } from '@/lib/trafficFormat'
import type { UserProvisioningCard, UserProvisionSummary } from '@/types'

const GIGABYTE = 1024 ** 3

interface UserAccessControlSectionProps {
  card: UserProvisioningCard
  onRefresh: () => void
}

/** Продление доступа и приостановка (модуль «Пользователи (абоненты)»). */
function AccessLifecycleCard({
  user,
  busy,
  onExtend,
  onSuspend,
  onResume,
  onError,
}: {
  user: UserProvisionSummary
  busy: boolean
  onExtend: (days: number) => void
  onSuspend: (data: { reason: string | null; show_reason: boolean; notify_telegram: boolean }) => void
  onResume: (notifyTelegram: boolean) => void
  onError: (message: string) => void
}) {
  const [suspendOpen, setSuspendOpen] = useState(false)
  const [suspendReason, setSuspendReason] = useState('')
  const [showReason, setShowReason] = useState(false)
  const [suspendNotify, setSuspendNotify] = useState(false)
  const [resumeNotify, setResumeNotify] = useState(false)
  const [customDays, setCustomDays] = useState('')

  const suspended = Boolean(user.suspended_at)
  // Администраторов приостановить нельзя (API отклоняет) — прячем действие.
  const canSuspend = user.role !== 'admin'

  const handleCustomExtend = () => {
    const days = Number.parseInt(customDays, 10)
    if (!Number.isFinite(days) || days < 1 || days > 3650) {
      onError('Укажите число дней от 1 до 3650')
      return
    }
    onExtend(days)
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <CalendarPlus size={16} />
            Продление и приостановка
          </CardTitle>
          <CardDescription>
            Продление отсчитывается от max(сейчас, текущий срок) и сбрасывает счётчик трафика.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => onExtend(30)}
              disabled={busy}
            >
              +30 дней
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => onExtend(60)}
              disabled={busy}
            >
              +60 дней
            </Button>
            <div className="flex items-center gap-1.5">
              <Input
                value={customDays}
                onChange={(e) => setCustomDays(e.target.value)}
                placeholder="дней"
                inputMode="numeric"
                aria-label="Свой срок продления в днях"
                className="h-9 w-24"
              />
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={handleCustomExtend}
                disabled={busy || customDays.trim() === ''}
              >
                Продлить
              </Button>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 border-t pt-3">
            {suspended ? (
              <>
                <Badge variant="destructive" className="text-[10px]">
                  Приостановлен
                </Badge>
                <Button type="button" size="sm" onClick={() => onResume(resumeNotify)} disabled={busy}>
                  <PlayCircle size={15} />
                  Возобновить доступ
                </Button>
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Checkbox
                    checked={resumeNotify}
                    onCheckedChange={(value) => setResumeNotify(value === true)}
                    aria-label="Уведомить в Telegram о возобновлении"
                  />
                  Уведомить в Telegram
                </label>
              </>
            ) : canSuspend ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setSuspendOpen(true)}
                disabled={busy}
              >
                <PauseCircle size={15} />
                Приостановить доступ
              </Button>
            ) : null}
          </div>
          {suspended && user.suspend_reason && (
            <p className="text-xs text-muted-foreground">
              Причина: {user.suspend_reason}
              {user.suspend_reason_visible ? '' : ' (скрыта от пользователя)'}
            </p>
          )}
        </CardContent>
      </Card>

      <AppDialog
        open={suspendOpen}
        onOpenChange={setSuspendOpen}
        title="Приостановить доступ"
        description="Все конфиги абонента будут заблокированы до возобновления."
        icon={PauseCircle}
        size="md"
        footer={
          <>
            <Button type="button" variant="outline" onClick={() => setSuspendOpen(false)} disabled={busy}>
              Отмена
            </Button>
            <Button
              type="button"
              onClick={() => {
                onSuspend({
                  reason: suspendReason.trim() || null,
                  show_reason: showReason,
                  notify_telegram: suspendNotify,
                })
                setSuspendOpen(false)
                setSuspendReason('')
                setShowReason(false)
                setSuspendNotify(false)
              }}
              disabled={busy}
            >
              Приостановить
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="suspendReason">Причина (до 200 символов)</Label>
            <Input
              id="suspendReason"
              value={suspendReason}
              onChange={(e) => setSuspendReason(e.target.value.slice(0, 200))}
              placeholder="например: неоплата"
              maxLength={200}
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={showReason}
              onCheckedChange={(value) => setShowReason(value === true)}
              aria-label="Показать причину пользователю"
            />
            Показать причину пользователю
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={suspendNotify}
              onCheckedChange={(value) => setSuspendNotify(value === true)}
              aria-label="Уведомить в Telegram"
            />
            Уведомить в Telegram
          </label>
        </div>
      </AppDialog>
    </>
  )
}

/** Лимит трафика пользователя. */
function TrafficLimitCard({
  user,
  busy,
  trafficSyncOn,
  onSave,
  onClear,
  onResetCounter,
  onError,
}: {
  user: UserProvisionSummary
  busy: boolean
  trafficSyncOn: boolean
  onSave: (bytes: number) => void
  onClear: () => void
  onResetCounter: () => void
  onError: (message: string) => void
}) {
  const [trafficOpen, setTrafficOpen] = useState(false)
  const [trafficGb, setTrafficGb] = useState('')

  const limitBytes = user.traffic_limit_bytes ?? null
  const consumedBytes = user.traffic_consumed_bytes ?? 0

  const handleSave = (): boolean => {
    const gb = Number.parseFloat(trafficGb.replace(',', '.'))
    if (!Number.isFinite(gb) || gb <= 0) {
      onError('Укажите лимит трафика в ГБ (например, 100)')
      return false
    }
    onSave(Math.round(gb * GIGABYTE))
    return true
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <Gauge size={16} />
            Лимит трафика
          </CardTitle>
          <CardDescription>
            Общий лимит пользователя на все его конфиги. По умолчанию ограничений нет.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {!trafficSyncOn && (
            <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
              Модуль «Синхронизация трафика» выключен — учёт трафика не идёт, лимит не работает.
              Включите его в Настройках → Модули.
            </p>
          )}
          {limitBytes == null ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-muted-foreground">Без ограничения</span>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => {
                  setTrafficGb('')
                  setTrafficOpen(true)
                }}
                disabled={busy || !trafficSyncOn}
              >
                Задать лимит
              </Button>
            </div>
          ) : (
            <div className="space-y-2">
              <p className="text-sm">
                {formatBytes(consumedBytes)} из {formatBytes(limitBytes)}
                {user.traffic_counter_reset_at ? ` (с ${formatDate(user.traffic_counter_reset_at)})` : ''}
                {user.traffic_limit_blocked ? ' — лимит исчерпан, доступ заблокирован' : ''}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setTrafficGb(String(Math.round((limitBytes / GIGABYTE) * 100) / 100))
                    setTrafficOpen(true)
                  }}
                  disabled={busy || !trafficSyncOn}
                >
                  Изменить лимит
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={onResetCounter}
                  disabled={busy || !trafficSyncOn}
                >
                  <RotateCcw size={15} />
                  Сбросить счётчик
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={onClear} disabled={busy}>
                  Снять ограничение
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <AppDialog
        open={trafficOpen}
        onOpenChange={setTrafficOpen}
        title="Лимит трафика"
        description="Укажите лимит в гигабайтах. Счётчик отсчитывается с момента установки лимита."
        icon={Gauge}
        size="sm"
        footer={
          <>
            <Button type="button" variant="outline" onClick={() => setTrafficOpen(false)} disabled={busy}>
              Отмена
            </Button>
            <Button
              type="button"
              onClick={() => {
                if (handleSave()) setTrafficOpen(false)
              }}
              disabled={busy}
            >
              Сохранить
            </Button>
          </>
        }
      >
        <div className="space-y-1.5">
          <Label htmlFor="trafficLimitGb">Лимит, ГБ</Label>
          <Input
            id="trafficLimitGb"
            value={trafficGb}
            onChange={(e) => setTrafficGb(e.target.value)}
            inputMode="decimal"
            placeholder="100"
          />
        </div>
      </AppDialog>
    </>
  )
}

export default function UserAccessControlSection({
  card,
  onRefresh,
}: UserAccessControlSectionProps) {
  const { user } = card
  const { isEnabled } = useFeatureModules()
  const { success, error: notifyError } = useNotifications()
  const trafficSyncOn = isEnabled('traffic_sync')
  // Приостановка/продление — только при включённом модуле «Пользователи (абоненты)».
  const provisioningOn = isEnabled('user_provisioning')

  const [busy, setBusy] = useState(false)

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

  const handleExtend = (days: number) => {
    void run(async () => {
      await extendUserAccess(user.id, days)
    }, `Доступ продлён на ${days} дн.`)
  }

  const handleSuspend = (data: {
    reason: string | null
    show_reason: boolean
    notify_telegram: boolean
  }) => {
    void run(async () => {
      await suspendUser(user.id, data)
    }, 'Доступ приостановлен')
  }

  const handleResume = (notifyTelegram: boolean) => {
    void run(async () => {
      await resumeUser(user.id, { notify_telegram: notifyTelegram })
    }, 'Доступ возобновлён')
  }

  const handleSaveTraffic = (bytes: number) => {
    void run(async () => {
      await setUserTrafficLimit(user.id, bytes)
    }, 'Лимит трафика сохранён')
  }

  const handleClearTraffic = () => {
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
      {provisioningOn && (
        <AccessLifecycleCard
          user={user}
          busy={busy}
          onExtend={handleExtend}
          onSuspend={handleSuspend}
          onResume={handleResume}
          onError={notifyError}
        />
      )}
      <TrafficLimitCard
        user={user}
        busy={busy}
        trafficSyncOn={trafficSyncOn}
        onSave={handleSaveTraffic}
        onClear={handleClearTraffic}
        onResetCounter={handleResetCounter}
        onError={notifyError}
      />
    </div>
  )
}
