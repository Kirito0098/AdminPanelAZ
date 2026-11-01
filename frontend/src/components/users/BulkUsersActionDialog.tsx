import { useEffect, useState } from 'react'
import { Users } from 'lucide-react'
import { ApiError } from '@/api/client'
import { bulkUsers } from '@/api/users'
import AppDialog from '@/components/shared/AppDialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useNotifications } from '@/context/NotificationContext'
import type { BulkUsersAction, BulkUsersRequest, BulkUsersResult } from '@/types'

const ACTIONS: { id: BulkUsersAction; label: string; hint: string }[] = [
  { id: 'extend', label: 'Продлить доступ', hint: 'срок + N дней' },
  { id: 'suspend', label: 'Приостановить', hint: 'заблокировать конфиги' },
  { id: 'resume', label: 'Возобновить', hint: 'снять приостановку' },
  { id: 'set_traffic_limit', label: 'Задать лимит трафика', hint: 'общий на абонента' },
  { id: 'delete', label: 'Удалить', hint: 'необратимо' },
]

interface BulkUsersActionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  userIds: number[]
  onDone: () => void
}

export default function BulkUsersActionDialog({
  open,
  onOpenChange,
  userIds,
  onDone,
}: BulkUsersActionDialogProps) {
  const { error: notifyError, success } = useNotifications()
  const [action, setAction] = useState<BulkUsersAction>('extend')
  const [days, setDays] = useState('30')
  const [reason, setReason] = useState('')
  const [showReason, setShowReason] = useState(false)
  const [notifyTelegram, setNotifyTelegram] = useState(false)
  const [limitGb, setLimitGb] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<BulkUsersResult | null>(null)

  useEffect(() => {
    if (open) {
      setResult(null)
      setSubmitting(false)
    }
  }, [open])

  const gbToBytes = (gb: string): number | null => {
    const trimmed = gb.trim()
    if (!trimmed) return null
    const n = Number.parseFloat(trimmed)
    return Number.isFinite(n) && n >= 0 ? Math.round(n * 1024 ** 3) : null
  }

  const buildRequest = (): BulkUsersRequest => {
    const base: BulkUsersRequest = { action, user_ids: userIds }
    if (action === 'extend') base.days = Number.parseInt(days, 10) || 30
    if (action === 'suspend') {
      base.reason = reason.trim() || null
      base.show_reason = showReason
      base.notify_telegram = notifyTelegram
    }
    if (action === 'resume') base.notify_telegram = notifyTelegram
    if (action === 'set_traffic_limit') base.traffic_limit_bytes = gbToBytes(limitGb)
    return base
  }

  const handleSubmit = async () => {
    if (userIds.length === 0) return
    setSubmitting(true)
    try {
      const res = await bulkUsers(buildRequest())
      setResult(res)
      if (res.succeeded > 0) {
        success(`Выполнено: ${res.succeeded} из ${res.total}`)
        onDone()
      }
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка массовой операции')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AppDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Массовые действия"
      description={`Абонентов в выборке: ${userIds.length}`}
      icon={Users}
      size="lg"
    >
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="bulkAction">Действие</Label>
          <select
            id="bulkAction"
            value={action}
            onChange={(e) => setAction(e.target.value as BulkUsersAction)}
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            {ACTIONS.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label} — {a.hint}
              </option>
            ))}
          </select>
        </div>

        {action === 'extend' && (
          <div className="space-y-1.5">
            <Label htmlFor="bulkDays">Дней</Label>
            <Input
              id="bulkDays"
              type="number"
              min={1}
              value={days}
              onChange={(e) => setDays(e.target.value)}
              className="h-9 w-32"
            />
          </div>
        )}

        {action === 'suspend' && (
          <div className="space-y-2">
            <div className="space-y-1.5">
              <Label htmlFor="bulkReason">Причина (необязательно)</Label>
              <Input
                id="bulkReason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="h-9"
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={showReason} onCheckedChange={(v) => setShowReason(v === true)} />
              Показывать причину абоненту
            </label>
          </div>
        )}

        {(action === 'suspend' || action === 'resume') && (
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={notifyTelegram}
              onCheckedChange={(v) => setNotifyTelegram(v === true)}
            />
            Уведомить в Telegram
          </label>
        )}

        {action === 'set_traffic_limit' && (
          <div className="space-y-1.5">
            <Label htmlFor="bulkLimit">Лимит, ГБ (пусто — снять)</Label>
            <Input
              id="bulkLimit"
              inputMode="decimal"
              value={limitGb}
              onChange={(e) => setLimitGb(e.target.value)}
              placeholder="100"
              className="h-9 w-32"
            />
          </div>
        )}

        {action === 'delete' && (
          <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive">
            Удаление необратимо: {userIds.length} абонент(ов) и их конфиги будут удалены.
          </p>
        )}

        {result && (
          <div className="rounded-lg border bg-muted/20 p-2 text-sm">
            <p>
              Успешно: {result.succeeded} · Ошибок: {result.failed.length}
            </p>
            {result.failed.length > 0 && (
              <ul className="mt-1 max-h-32 space-y-0.5 overflow-y-auto text-xs text-destructive">
                {result.failed.map((f) => (
                  <li key={f.user_id}>
                    {f.username || `#${f.user_id}`}: {f.error}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Отмена
          </Button>
          <Button
            type="button"
            variant={action === 'delete' ? 'destructive' : 'default'}
            onClick={() => void handleSubmit()}
            disabled={submitting || userIds.length === 0}
          >
            {submitting ? 'Выполнение…' : 'Применить'}
          </Button>
        </div>
        {userIds.length === 0 && (
          <p className="text-xs text-muted-foreground">
            Выберите абонентов или примените фильтр.
          </p>
        )}
      </div>
    </AppDialog>
  )
}