import { ChevronDown } from 'lucide-react'
import { useCallback } from 'react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

export type StaleFilter = 7 | 30 | 90 | 'never' | null

export interface UsersFiltersProps {
  filter: string
  onFilterChange: (value: string) => void
  stale: StaleFilter
  onStaleChange: (value: StaleFilter) => void
}

const STALE_OPTIONS: { value: Exclude<StaleFilter, null>; label: string }[] = [
  { value: 7, label: '7 дней' },
  { value: 30, label: '30 дней' },
  { value: 90, label: '90 дней' },
  { value: 'never', label: 'Никогда' },
]

const FILTERS: { id: string; label: string }[] = [
  { id: 'all', label: 'Все' },
  { id: 'attention', label: 'Требуют внимания' },
  { id: 'unmanaged', label: 'Без набора' },
  { id: 'expiring', label: 'Истекать ≤ 7 дн.' },
  { id: 'expired', label: 'Истёк' },
  { id: 'suspended', label: 'Приостановлены' },
  { id: 'inactive', label: 'Отключены' },
  { id: 'deleting', label: 'Удаляется' },
]

export const USERS_FILTER_IDS: readonly string[] = FILTERS.map((item) => item.id)

export function UsersFilters({
  filter,
  onFilterChange,
  stale,
  onStaleChange,
}: UsersFiltersProps) {
  const handleClick = useCallback(
    (id: string) => () => {
      onFilterChange(id)
    },
    [onFilterChange],
  )

  return (
    <div className="flex flex-wrap gap-1" role="group" aria-label="Фильтры пользователей">
      {FILTERS.map((item) => (
        <Button
          key={item.id}
          type="button"
          size="sm"
          variant={filter === item.id ? 'default' : 'outline'}
          className="h-8 text-xs shrink-0"
          onClick={handleClick(item.id)}
          aria-pressed={filter === item.id}
        >
          {item.label}
        </Button>
      ))}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            size="sm"
            variant={stale == null ? 'outline' : 'default'}
            className="h-8 shrink-0 gap-1 text-xs"
            aria-pressed={stale != null}
            aria-label="Фильтр по последней активности"
          >
            {stale == null ? 'Не заходил' : 'Не заходил: выбран'}
            <ChevronDown size={12} />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-44">
          {STALE_OPTIONS.map((option) => (
            <DropdownMenuItem key={option.value} onClick={() => onStaleChange(option.value)}>
              {option.label}
            </DropdownMenuItem>
          ))}
          {stale != null && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => onStaleChange(null)}>Сбросить</DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
