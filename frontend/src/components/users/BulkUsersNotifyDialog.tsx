import { useMemo, useState } from 'react'
import { ApiError } from '@/api/client'
import { startBulkNotify } from '@/api/users'
import AppDialog from '@/components/shared/AppDialog'
import { Button } from '@/components/ui/button'
import { useNotifications } from '@/context/NotificationContext'
import type { User } from '@/types'

const MAX_LEN = 1000

interface BulkUsersNotifyDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  users: User[]
  selectedIds: number[]
  onStarted: (taskId: string) => void
}

/** Текст и предпросмотр аудитории; отправка — фоновой задачей. */
export default function BulkUsersNotifyDialog({
  open,
  onOpenChange,
  users,
  selectedIds,
  onStarted,
}: BulkUsersNotifyDialogProps) {
  const { error: notifyError } = useNotifications()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)

  const target = useMemo(
    () => (selectedIds.length > 0 ? users.filter((u) => selectedIds.includes(u.id)) : users),
    [users, selectedIds],
  )
  const withTelegram = target.filter((u) => (u.telegram_id ?? '').trim()).length
  const withoutTelegram = target.length - withTelegram

  const handleSubmit = async () => {
    const value = text.trim()
    if (!value) return
    setBusy(true)
    try {
      const { task_id } = await startBulkNotify({
        user_ids: target.map((u) => u.id),
        text: value,
      })
      setText('')
      onOpenChange(false)
      onStarted(task_id)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось запустить рассылку')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AppDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Уведомить в Telegram"
      description="Сообщение получат только абоненты с привязанным Telegram"
      size="lg"
    >
      <div className="space-y-4">
        <div className="rounded-lg border bg-muted/30 p-3 text-sm">
          Затронуто: <strong>{target.length}</strong> · с Telegram:{' '}
          <strong>{withTelegram}</strong> · без Telegram: <strong>{withoutTelegram}</strong>
        </div>
        <div className="space-y-1.5">
          <label htmlFor="bulk-notify-text" className="text-sm font-medium">
            Текст сообщения
          </label>
          <textarea
            id="bulk-notify-text"
            value={text}
            onChange={(e) => setText(e.target.value.slice(0, MAX_LEN))}
            rows={6}
            maxLength={MAX_LEN}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            placeholder="Например: завтра с 03:00 до 04:00 возможны перебои…"
          />
          <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>Получатель увидит подпись «📢 Уведомление от администратора» и ниже ваш текст</span>
            <span>
              {text.length} / {MAX_LEN}
            </span>
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Отмена
          </Button>
          <Button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={busy || !text.trim() || withTelegram === 0}
          >
            {busy ? 'Запуск…' : 'Отправить'}
          </Button>
        </div>
      </div>
    </AppDialog>
  )
}
