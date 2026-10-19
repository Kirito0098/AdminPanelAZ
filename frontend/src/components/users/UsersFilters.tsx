import { useCallback } from 'react'
import { Button } from '@/components/ui/button'

export interface UsersFiltersProps {
  filter: string
  onFilterChange: (value: string) => void
}

const FILTERS: { id: string; label: string }[] = [
  { id: 'all', label: 'Все' },
  { id: 'attention', label: 'Требуют внимания' },
  { id: 'unmanaged', label: 'Без набора' },
  { id: 'expiring', label: 'Истекать ≤ 7 дн.' },
  { id: 'expired', label: 'Истёк' },
  { id: 'suspended', label: 'Приостановлены' },
]

export function UsersFilters({ filter, onFilterChange }: UsersFiltersProps) {
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
    </div>
  )
}
