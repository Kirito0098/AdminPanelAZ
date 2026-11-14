import type { ReactNode } from 'react'
import { RotateCcw, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { providerCategoryLabel } from './utils'

export interface ProviderFilterStatusOption {
  value: string
  label: string
}

interface ProviderFilterBarProps {
  query: string
  onQueryChange: (value: string) => void
  category: string
  onCategoryChange: (value: string) => void
  /** Категории без служебного `all` — чип «Все» добавляется сам. */
  categories: readonly string[]
  categoryCounts?: Readonly<Record<string, number>>
  status?: string
  onStatusChange?: (value: string) => void
  statusOptions?: readonly ProviderFilterStatusOption[]
  /** Правый слот: действия по текущему фильтру (порог, «только категория» и т.п.). */
  extra?: ReactNode
  resultCount: number
  totalCount: number
  disabled?: boolean
  placeholder?: string
}

/** Один фильтр провайдеров для всех вкладок маршрутизации: поиск, чипы категорий, статус. */
export default function ProviderFilterBar({
  query,
  onQueryChange,
  category,
  onCategoryChange,
  categories,
  categoryCounts,
  status,
  onStatusChange,
  statusOptions,
  extra,
  resultCount,
  totalCount,
  disabled = false,
  placeholder = 'Поиск по имени или категории…',
}: ProviderFilterBarProps) {
  const statusFilter = status ?? 'all'
  const hasFilters = query.trim() !== '' || category !== 'all' || statusFilter !== 'all'

  const resetFilters = () => {
    onQueryChange('')
    onCategoryChange('all')
    onStatusChange?.('all')
  }

  const chips: Array<{ value: string; label: string; count: number | undefined }> = [
    { value: 'all', label: 'Все', count: totalCount },
    ...categories.map((value) => ({
      value,
      label: providerCategoryLabel(value),
      count: categoryCounts?.[value],
    })),
  ]

  const showStatus = onStatusChange != null && (statusOptions?.length ?? 0) > 0

  return (
    <div className="space-y-2">
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <div className="relative w-full min-w-0 sm:max-w-sm sm:flex-1">
          <Search
            size={14}
            aria-hidden="true"
            className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            type="search"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder={placeholder}
            aria-label="Поиск провайдеров"
            className="h-9 w-full pl-9"
            disabled={disabled}
          />
        </div>
        {showStatus && onStatusChange && (
          <Select value={statusFilter} onValueChange={onStatusChange} disabled={disabled}>
            <SelectTrigger className="w-full sm:w-[170px]" aria-label="Статус обновления в БД">
              <SelectValue placeholder="Статус БД" />
            </SelectTrigger>
            <SelectContent>
              {statusOptions?.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        {extra && <div className="flex flex-wrap items-center gap-2 sm:ml-auto">{extra}</div>}
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {chips.map((chip) => {
          const active = category === chip.value
          return (
            <button
              key={chip.value}
              type="button"
              disabled={disabled}
              aria-pressed={active}
              onClick={() => onCategoryChange(chip.value)}
              className={cn(
                'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                active
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-border bg-muted/30 text-muted-foreground hover:bg-muted/60 hover:text-foreground',
                disabled && 'pointer-events-none opacity-50',
              )}
            >
              {chip.label}
              {chip.count != null && <span className="ml-1 opacity-70">({chip.count})</span>}
            </button>
          )
        })}
        {hasFilters && (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-7 px-2 text-xs"
            disabled={disabled}
            onClick={resetFilters}
          >
            <RotateCcw size={12} className="mr-1" aria-hidden="true" />
            Сбросить
          </Button>
        )}
        <span className="ml-auto text-xs tabular-nums text-muted-foreground">
          Показано: {resultCount} из {totalCount}
        </span>
      </div>
    </div>
  )
}
