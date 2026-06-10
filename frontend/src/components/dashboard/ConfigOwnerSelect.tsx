import { useMemo } from 'react'
import { configOwnerCandidates, formatOwnerLabel, resolveOwnerOptions } from '@/lib/configOwners'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { User } from '@/types'

interface ConfigOwnerSelectProps {
  id?: string
  users: User[]
  value: number | null
  onChange: (ownerId: number) => void
  disabled?: boolean
  label?: string
  description?: string
  currentOwner?: { id: number; username: string }
}

export default function ConfigOwnerSelect({
  id = 'configOwner',
  users,
  value,
  onChange,
  disabled = false,
  label = 'Владелец',
  description,
  currentOwner,
}: ConfigOwnerSelectProps) {
  const options = useMemo(
    () => resolveOwnerOptions(users, value, currentOwner),
    [users, value, currentOwner],
  )
  const activeIds = useMemo(
    () => new Set(configOwnerCandidates(users).map((user) => user.id)),
    [users],
  )

  if (options.length === 0) {
    return null
  }

  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      {description && <p className="text-xs text-muted-foreground">{description}</p>}
      <Select
        value={value ? String(value) : undefined}
        onValueChange={(next) => onChange(Number(next))}
        disabled={disabled}
      >
        <SelectTrigger id={id}>
          <SelectValue placeholder="Выберите владельца" />
        </SelectTrigger>
        <SelectContent>
          {options.map((user) => (
            <SelectItem key={user.id} value={String(user.id)} disabled={!activeIds.has(user.id)}>
              {formatOwnerLabel(user, !activeIds.has(user.id))}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
