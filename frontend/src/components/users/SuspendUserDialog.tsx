import { useEffect, useState } from 'react'
import { PauseCircle } from 'lucide-react'
import AppDialog from '@/components/shared/AppDialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export interface SuspendUserPayload {
  reason: string | null
  show_reason: boolean
  notify_telegram: boolean
}

interface SuspendUserDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Логин абонента — попадает в описание диалога. */
  username: string
  busy?: boolean
  onConfirm: (data: SuspendUserPayload) => void
}

/**
 * Приостановка доступа: причина, показ её абоненту и уведомление в Telegram.
 *
 * Причина видна абоненту, а уведомление включено по умолчанию: после закрытия
 * доступа человек должен узнать, почему. Админ снимает галочки, если причина
 * внутренняя или писать не нужно.
 */
export default function SuspendUserDialog({
  open,
  onOpenChange,
  username,
  busy = false,
  onConfirm,
}: SuspendUserDialogProps) {
  const [reason, setReason] = useState('')
  const [showReason, setShowReason] = useState(true)
  const [notifyTelegram, setNotifyTelegram] = useState(true)

  useEffect(() => {
    if (!open) return
    setReason('')
    setShowReason(true)
    setNotifyTelegram(true)
  }, [open])

  return (
    <AppDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Приостановить доступ"
      description={`Все конфиги абонента «${username}» будут заблокированы до возобновления.`}
      icon={PauseCircle}
      size="md"
      footer={
        <>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            Отмена
          </Button>
          <Button
            type="button"
            onClick={() => {
              onConfirm({
                reason: reason.trim() || null,
                show_reason: showReason,
                notify_telegram: notifyTelegram,
              })
              onOpenChange(false)
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
            value={reason}
            onChange={(e) => setReason(e.target.value.slice(0, 200))}
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
            checked={notifyTelegram}
            onCheckedChange={(value) => setNotifyTelegram(value === true)}
            aria-label="Уведомить в Telegram"
          />
          Уведомить в Telegram
        </label>
      </div>
    </AppDialog>
  )
}
