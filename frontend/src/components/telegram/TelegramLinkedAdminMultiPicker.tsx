import { Link } from 'react-router-dom'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import type { User } from '@/types'

export interface TelegramLinkedAdminMultiPickerProps {
  id: string
  label: string
  hint: string
  admins: User[]
  mode: 'telegram_id' | 'user_id'
  selectedTelegramIds?: string[]
  selectedUserIds?: number[]
  onTelegramIdsChange?: (ids: string[]) => void
  onUserIdsChange?: (ids: number[]) => void
  allowManual?: boolean
  manualPlaceholder?: string
  manualHint?: string
}

export default function TelegramLinkedAdminMultiPicker({
  id,
  label,
  hint,
  admins,
  mode,
  selectedTelegramIds = [],
  selectedUserIds = [],
  onTelegramIdsChange,
  onUserIdsChange,
  allowManual = false,
  manualPlaceholder = '123456789',
  manualHint,
}: TelegramLinkedAdminMultiPickerProps) {
  const selectedIds = mode === 'telegram_id' ? selectedTelegramIds : selectedUserIds.map(String)
  const adminTelegramIds = new Set(admins.map((admin) => admin.telegram_id!).filter(Boolean))
  const manualIds = mode === 'telegram_id'
    ? selectedTelegramIds.filter((item) => !adminTelegramIds.has(item))
    : []

  const toggleAdmin = (admin: User, checked: boolean) => {
    if (mode === 'telegram_id') {
      const tgId = admin.telegram_id!
      const next = checked
        ? [...new Set([...selectedTelegramIds, tgId])]
        : selectedTelegramIds.filter((item) => item !== tgId)
      onTelegramIdsChange?.(next)
      return
    }
    const next = checked
      ? [...new Set([...selectedUserIds, admin.id])]
      : selectedUserIds.filter((item) => item !== admin.id)
    onUserIdsChange?.(next)
  }

  const isAdminSelected = (admin: User) =>
    mode === 'telegram_id'
      ? selectedTelegramIds.includes(admin.telegram_id!)
      : selectedUserIds.includes(admin.id)

  const setManualIds = (raw: string) => {
    if (mode !== 'telegram_id') return
    const manual = raw
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
    const fromAdmins = selectedTelegramIds.filter((item) => adminTelegramIds.has(item))
    onTelegramIdsChange?.([...new Set([...fromAdmins, ...manual])])
  }

  if (admins.length === 0) {
    return (
      <div className="space-y-2">
        <Label htmlFor={id}>{label}</Label>
        <SettingsAlert variant="warning" title="Нет администраторов с Telegram ID">
          Укажите Telegram ID в{' '}
          <Link to="/settings" className="font-medium text-primary underline-offset-4 hover:underline">
            Настройки → Пользователи
          </Link>{' '}
          для нужных администраторов.
        </SettingsAlert>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Label htmlFor={id}>{label}</Label>
        {selectedIds.length > 0 && (
          <Badge variant="outline">
            Выбрано: {selectedIds.length}
          </Badge>
        )}
      </div>

      <div className="space-y-2 rounded-lg border bg-muted/20 p-3">
        {admins.map((admin) => {
          const checked = isAdminSelected(admin)
          const checkboxId = `${id}-${admin.id}`
          return (
            <label
              key={admin.id}
              htmlFor={checkboxId}
              className={cn(
                'flex cursor-pointer items-start gap-3 rounded-md border p-3 transition-colors',
                checked ? 'border-primary/40 bg-primary/5' : 'border-transparent hover:bg-muted/40',
              )}
            >
              <Checkbox
                id={checkboxId}
                checked={checked}
                onCheckedChange={(value) => toggleAdmin(admin, value === true)}
                className="mt-0.5"
              />
              <div className="min-w-0">
                <p className="font-medium leading-snug">{admin.username}</p>
                <p className="font-mono text-xs text-muted-foreground">{admin.telegram_id}</p>
              </div>
            </label>
          )
        })}
      </div>

      {allowManual && mode === 'telegram_id' && (
        <div className="space-y-2">
          <Label htmlFor={`${id}-manual`}>Дополнительные chat ID</Label>
          <Input
            id={`${id}-manual`}
            value={manualIds.join(', ')}
            onChange={(e) => setManualIds(e.target.value)}
            placeholder={manualPlaceholder}
            className="font-mono text-sm"
          />
          {manualHint && <p className="text-xs text-muted-foreground">{manualHint}</p>}
        </div>
      )}

      <p className="text-xs text-muted-foreground">{hint}</p>
    </div>
  )
}
