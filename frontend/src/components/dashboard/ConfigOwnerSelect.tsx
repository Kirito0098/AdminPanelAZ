import { useMemo, useState } from 'react'
import { configOwnerCandidates, formatOwnerLabel, resolveOwnerOptions } from '@/lib/configOwners'
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

/** До этого числа владельцев список короткий и поиск только мешает. */
const SEARCH_THRESHOLD = 8

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
  const [query, setQuery] = useState('')
  const normalizedQuery = query.trim().toLowerCase()

  const filtered = useMemo(() => {
    if (!normalizedQuery) return options
    const matched = options.filter((user) =>
      formatOwnerLabel(user, !activeIds.has(user.id)).toLowerCase().includes(normalizedQuery),
    )
    // Текущий владелец остаётся в списке при любом фильтре: иначе триггер
    // потеряет подпись, а выбор нельзя будет увидеть.
    const selected = options.find((user) => user.id === value)
    if (selected && !matched.some((user) => user.id === selected.id)) matched.unshift(selected)
    return matched
  }, [options, normalizedQuery, activeIds, value])

  if (options.length === 0) {
    return null
  }

  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      {description && <p className="text-xs text-muted-foreground">{description}</p>}
      {options.length > SEARCH_THRESHOLD && (
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Поиск по логину"
          aria-label="Поиск владельца"
          autoComplete="off"
          className="h-9"
        />
      )}
      {filtered.length === 0 ? (
        <p className="text-xs text-muted-foreground">Никого не нашли — измените запрос.</p>
      ) : (
        <Select
          value={value ? String(value) : undefined}
          onValueChange={(next) => {
            onChange(Number(next))
            setQuery('')
          }}
          disabled={disabled}
        >
          <SelectTrigger id={id}>
            <SelectValue placeholder="Выберите владельца" />
          </SelectTrigger>
          <SelectContent>
            {filtered.map((user) => (
              <SelectItem key={user.id} value={String(user.id)} disabled={!activeIds.has(user.id)}>
                {formatOwnerLabel(user, !activeIds.has(user.id))}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </div>
  )
}
