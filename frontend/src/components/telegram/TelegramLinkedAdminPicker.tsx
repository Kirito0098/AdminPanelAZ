import { Link } from 'react-router-dom'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { User } from '@/types'

const CUSTOM_VALUE = '__custom__'

export interface TelegramLinkedAdminPickerProps {
  id: string
  label: string
  hint: string
  value: string
  onChange: (value: string) => void
  admins: User[]
  allowManual?: boolean
  manualPlaceholder?: string
  manualHint?: string
}

export default function TelegramLinkedAdminPicker({
  id,
  label,
  hint,
  value,
  onChange,
  admins,
  allowManual = false,
  manualPlaceholder = '123456789',
  manualHint,
}: TelegramLinkedAdminPickerProps) {
  const matchedAdmin = admins.find((admin) => admin.telegram_id === value)
  const selectValue = matchedAdmin
    ? matchedAdmin.telegram_id!
    : allowManual
      ? value
        ? CUSTOM_VALUE
        : undefined
      : undefined

  if (admins.length === 0) {
    return (
      <div className="space-y-2">
        <Label htmlFor={id}>{label}</Label>
        {allowManual ? (
          <Input
            id={id}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={manualPlaceholder}
          />
        ) : (
          <SettingsAlert variant="warning" title="Нет администраторов с Telegram ID">
            Укажите Telegram ID в{' '}
            <Link to="/settings/users" className="font-medium text-primary underline-offset-4 hover:underline">
              Настройки → Пользователи
            </Link>{' '}
            для нужного администратора.
          </SettingsAlert>
        )}
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>
    )
  }

  const showManualInput = allowManual && (selectValue === CUSTOM_VALUE || (!matchedAdmin && Boolean(value)))

  if (!allowManual && value && !matchedAdmin) {
    return (
      <div className="space-y-2">
        <Label htmlFor={id}>{label}</Label>
        <SettingsAlert variant="warning" title="Telegram ID не привязан к администратору">
          Текущий ID <code className="font-mono">{value}</code> не найден среди администраторов. Выберите из списка
          ниже или обновите профиль в{' '}
          <Link to="/settings/users" className="font-medium text-primary underline-offset-4 hover:underline">
            Пользователях
          </Link>
          .
        </SettingsAlert>
        <Select
          value={undefined}
          onValueChange={(next) => onChange(next)}
        >
          <SelectTrigger id={id}>
            <SelectValue placeholder="Выберите администратора" />
          </SelectTrigger>
          <SelectContent>
            {admins.map((admin) => (
              <SelectItem key={admin.id} value={admin.telegram_id!}>
                {admin.username} · {admin.telegram_id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Select
        value={selectValue}
        onValueChange={(next) => {
          if (next === CUSTOM_VALUE) {
            onChange('')
            return
          }
          onChange(next)
        }}
      >
        <SelectTrigger id={id}>
          <SelectValue placeholder="Выберите администратора" />
        </SelectTrigger>
        <SelectContent>
          {admins.map((admin) => (
            <SelectItem key={admin.id} value={admin.telegram_id!}>
              {admin.username} · {admin.telegram_id}
            </SelectItem>
          ))}
          {allowManual && <SelectItem value={CUSTOM_VALUE}>Другой chat ID…</SelectItem>}
        </SelectContent>
      </Select>
      {showManualInput && (
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={manualPlaceholder}
          className="font-mono text-sm"
        />
      )}
      <p className="text-xs text-muted-foreground">{showManualInput && manualHint ? manualHint : hint}</p>
    </div>
  )
}
