import { Archive, Bell, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import type { User } from '@/types'

export interface TelegramRecipientsPanelProps {
  admins: User[]
  notifyRecipientIds: number[]
  onNotifyRecipientIdsChange: (ids: number[]) => void
  chatIds: string[]
  onChatIdsChange: (ids: string[]) => void
}

function adminTelegramIdSet(admins: User[]) {
  return new Set(admins.map((admin) => admin.telegram_id!).filter(Boolean))
}

export default function TelegramRecipientsPanel({
  admins,
  notifyRecipientIds,
  onNotifyRecipientIdsChange,
  chatIds,
  onChatIdsChange,
}: TelegramRecipientsPanelProps) {
  const linkedTelegramIds = adminTelegramIdSet(admins)
  const manualChatIds = chatIds.filter((item) => !linkedTelegramIds.has(item))
  const adminChatIds = chatIds.filter((item) => linkedTelegramIds.has(item))

  const toggleNotify = (admin: User, checked: boolean) => {
    const next = checked
      ? [...new Set([...notifyRecipientIds, admin.id])]
      : notifyRecipientIds.filter((id) => id !== admin.id)
    onNotifyRecipientIdsChange(next)
  }

  const toggleBackup = (admin: User, checked: boolean) => {
    const tgId = admin.telegram_id!
    const next = checked
      ? [...new Set([...chatIds, tgId])]
      : chatIds.filter((item) => item !== tgId)
    onChatIdsChange(next)
  }

  const selectAllNotify = () => onNotifyRecipientIdsChange(admins.map((admin) => admin.id))
  const selectAllBackup = () =>
    onChatIdsChange([...new Set([...admins.map((admin) => admin.telegram_id!), ...manualChatIds])])
  const clearNotify = () => onNotifyRecipientIdsChange([])
  const clearBackup = () => onChatIdsChange(manualChatIds)
  const syncBackupFromNotify = () => {
    const fromNotify = admins
      .filter((admin) => notifyRecipientIds.includes(admin.id))
      .map((admin) => admin.telegram_id!)
      .filter(Boolean)
    onChatIdsChange([...new Set([...fromNotify, ...manualChatIds])])
  }

  const setManualChatIds = (raw: string) => {
    const manual = raw
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
    onChatIdsChange([...new Set([...adminChatIds, ...manual])])
  }

  if (admins.length === 0) {
    return (
      <div className="space-y-3 rounded-lg border bg-muted/20 p-4">
        <div className="flex items-center gap-2">
          <Users size={16} className="text-muted-foreground" />
          <p className="text-sm font-medium">Получатели</p>
        </div>
        <SettingsAlert variant="warning" title="Нет администраторов с Telegram ID">
          Укажите Telegram ID в{' '}
          <Link to="/settings/users" className="font-medium text-primary underline-offset-4 hover:underline">
            Настройки → Пользователи
          </Link>{' '}
          для нужных администраторов.
        </SettingsAlert>
      </div>
    )
  }

  const notifyCount = notifyRecipientIds.length
  const backupAdminCount = adminChatIds.length
  const backupTotalCount = chatIds.length

  return (
    <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Users size={16} className="text-muted-foreground" />
            <p className="text-sm font-medium">Получатели</p>
          </div>
          <p className="text-xs text-muted-foreground">
            Отметьте, кто получает алерты и архивы бэкапов. Можно выбрать нескольких.
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {notifyCount > 0 && (
            <Badge variant="outline" className="gap-1">
              <Bell size={12} />
              {notifyCount}
            </Badge>
          )}
          {backupTotalCount > 0 && (
            <Badge variant="outline" className="gap-1">
              <Archive size={12} />
              {backupTotalCount}
            </Badge>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={selectAllNotify}>
          Все — уведомления
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={selectAllBackup}>
          Все — бэкапы
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={syncBackupFromNotify}>
          Бэкапы как уведомления
        </Button>
        {(notifyCount > 0 || backupAdminCount > 0) && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            onClick={() => {
              clearNotify()
              clearBackup()
            }}
          >
            Сбросить
          </Button>
        )}
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        {admins.map((admin) => {
          const notifyChecked = notifyRecipientIds.includes(admin.id)
          const backupChecked = chatIds.includes(admin.telegram_id!)
          return (
            <div
              key={admin.id}
              className={cn(
                'rounded-lg border bg-background/60 p-3 transition-colors',
                (notifyChecked || backupChecked) && 'border-primary/30 bg-primary/5',
              )}
            >
              <div className="mb-3 min-w-0">
                <p className="truncate font-medium leading-snug">{admin.username}</p>
                <p className="font-mono text-xs text-muted-foreground">{admin.telegram_id}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <label
                  htmlFor={`notify-${admin.id}`}
                  className={cn(
                    'flex flex-1 min-w-[7.5rem] cursor-pointer items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs transition-colors',
                    notifyChecked
                      ? 'border-sky-500/40 bg-sky-500/10 text-foreground'
                      : 'border-transparent bg-muted/40 text-muted-foreground hover:bg-muted/60',
                  )}
                >
                  <Checkbox
                    id={`notify-${admin.id}`}
                    checked={notifyChecked}
                    onCheckedChange={(value) => toggleNotify(admin, value === true)}
                    className="h-3.5 w-3.5 rounded-[3px]"
                  />
                  <Bell size={13} className="shrink-0" />
                  <span>Уведомления</span>
                </label>
                <label
                  htmlFor={`backup-${admin.id}`}
                  className={cn(
                    'flex flex-1 min-w-[7.5rem] cursor-pointer items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs transition-colors',
                    backupChecked
                      ? 'border-emerald-500/40 bg-emerald-500/10 text-foreground'
                      : 'border-transparent bg-muted/40 text-muted-foreground hover:bg-muted/60',
                  )}
                >
                  <Checkbox
                    id={`backup-${admin.id}`}
                    checked={backupChecked}
                    onCheckedChange={(value) => toggleBackup(admin, value === true)}
                    className="h-3.5 w-3.5 rounded-[3px]"
                  />
                  <Archive size={13} className="shrink-0" />
                  <span>Бэкапы</span>
                </label>
              </div>
            </div>
          )
        })}
      </div>

      <div className="space-y-2 rounded-lg border border-dashed bg-background/40 p-3">
        <Label htmlFor="manual-chat-ids" className="text-xs font-medium">
          Группа или канал для бэкапов <span className="font-normal text-muted-foreground">(необязательно)</span>
        </Label>
        <Input
          id="manual-chat-ids"
          value={manualChatIds.join(', ')}
          onChange={(e) => setManualChatIds(e.target.value)}
          placeholder="-1001234567890"
          className="h-9 font-mono text-sm"
        />
        <p className="text-xs text-muted-foreground">
          Chat ID через запятую — если архивы нужны в общий чат, а не в личку администратора.
        </p>
      </div>
    </div>
  )
}
