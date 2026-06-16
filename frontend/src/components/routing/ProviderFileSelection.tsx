import { useMemo, useState } from 'react'
import { Check, CloudDownload, Search } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import type { CidrDbStatus, CidrProviderInfo } from '@/types'
import {
  formatCompactCount,
  providerCategoryLabel,
  providerSlug,
  providerStatusTone,
  statusBadgeVariant,
  statusLabel,
} from './utils'

const CATEGORY_FILTERS = ['all', 'cdn', 'cloud', 'hosting'] as const
type CategoryFilter = (typeof CATEGORY_FILTERS)[number]

const STATUS_RING: Record<ReturnType<typeof providerStatusTone>, string> = {
  ok: 'border-emerald-500/30',
  warn: 'border-amber-500/40',
  error: 'border-destructive/50',
  muted: 'border-border',
}

const STATUS_DOT: Record<ReturnType<typeof providerStatusTone>, string> = {
  ok: 'bg-emerald-500',
  warn: 'bg-amber-500',
  error: 'bg-destructive',
  muted: 'bg-muted-foreground/40',
}

interface ProviderFileSelectionProps {
  providers: CidrProviderInfo[]
  cidrDb: CidrDbStatus | null
  selectedFiles: string[]
  onSelectedFilesChange: (files: string[]) => void
  disabled?: boolean
  idPrefix?: string
  onRefreshOne?: (filename: string) => void
  showQuickIngest?: boolean
}

export default function ProviderFileSelection({
  providers,
  cidrDb,
  selectedFiles,
  onSelectedFilesChange,
  disabled = false,
  idPrefix = 'provider-file',
  onRefreshOne,
  showQuickIngest = false,
}: ProviderFileSelectionProps) {
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>('all')

  const selectedSet = new Set(selectedFiles)
  const allFilenames = providers.map((p) => p.filename)

  const toggleFile = (filename: string) => {
    if (selectedSet.has(filename)) {
      onSelectedFilesChange(selectedFiles.filter((f) => f !== filename))
    } else {
      onSelectedFilesChange([...new Set([...selectedFiles, filename])])
    }
  }

  const selectAll = () => onSelectedFilesChange([...allFilenames])
  const selectNone = () => onSelectedFilesChange([])
  const selectFailed = () => {
    const failed = providers
      .filter((p) => cidrDb?.providers?.[p.filename]?.refresh_status === 'error')
      .map((p) => p.filename)
    onSelectedFilesChange(failed)
  }

  const selectByCategory = (category: CategoryFilter) => {
    if (category === 'all') {
      selectAll()
      return
    }
    onSelectedFilesChange(providers.filter((p) => p.category === category).map((p) => p.filename))
  }

  const failedCount = providers.filter(
    (p) => cidrDb?.providers?.[p.filename]?.refresh_status === 'error',
  ).length

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return providers.filter((p) => {
      if (categoryFilter !== 'all' && p.category !== categoryFilter) return false
      if (!q) return true
      const slug = providerSlug(p.filename)
      return (
        p.name.toLowerCase().includes(q) ||
        slug.includes(q) ||
        p.category.toLowerCase().includes(q) ||
        providerCategoryLabel(p.category).toLowerCase().includes(q)
      )
    })
  }, [providers, search, categoryFilter])

  const selectedCidrTotal = useMemo(
    () =>
      selectedFiles.reduce(
        (sum, filename) => sum + (cidrDb?.providers?.[filename]?.cidr_count ?? 0),
        0,
      ),
    [cidrDb?.providers, selectedFiles],
  )

  return (
    <div className="space-y-4 rounded-lg border bg-card/40 p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-1">
          <div className="text-sm font-semibold tracking-tight">Выбор провайдеров</div>
          <p className="text-xs text-muted-foreground max-w-xl">
            Отметьте одного или нескольких — необязательно обновлять все 12. Технический ID скрыт;
            на узле используются файлы вида <span className="font-mono">AP-…-include-ips.txt</span>.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="secondary" disabled={disabled} onClick={selectAll}>
            Все ({providers.length})
          </Button>
          <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={selectNone}>
            Снять
          </Button>
          {failedCount > 0 && (
            <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={selectFailed}>
              Ошибки ({failedCount})
            </Button>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1 max-w-md">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск: Akamai, cloud, hosting…"
            className="h-9 pl-9"
            disabled={disabled}
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {CATEGORY_FILTERS.map((cat) => {
            const label = cat === 'all' ? 'Все' : providerCategoryLabel(cat)
            const count =
              cat === 'all'
                ? providers.length
                : providers.filter((p) => p.category === cat).length
            const active = categoryFilter === cat
            return (
              <button
                key={cat}
                type="button"
                disabled={disabled}
                onClick={() => setCategoryFilter(cat)}
                onDoubleClick={() => !disabled && selectByCategory(cat)}
                title={cat === 'all' ? undefined : `Двойной щелчок — выбрать только ${label}`}
                className={cn(
                  'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                  active
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-border bg-muted/30 text-muted-foreground hover:bg-muted/60 hover:text-foreground',
                  disabled && 'opacity-50 pointer-events-none',
                )}
              >
                {label} ({count})
              </button>
            )
          })}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
        {filtered.map((provider) => {
          const dbMeta = cidrDb?.providers?.[provider.filename]
          const selected = selectedSet.has(provider.filename)
          const inputId = `${idPrefix}-${provider.filename}`
          const slug = providerSlug(provider.filename)
          const tone = providerStatusTone(dbMeta?.refresh_status)
          const cidrCount = dbMeta?.cidr_count

          return (
            <div
              key={provider.filename}
              role="button"
              tabIndex={disabled ? -1 : 0}
              aria-pressed={selected}
              aria-labelledby={`${inputId}-title`}
              title={`ID: ${slug} · файл списка: ${provider.filename}`}
              onClick={() => !disabled && toggleFile(provider.filename)}
              onKeyDown={(e) => {
                if (disabled) return
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  toggleFile(provider.filename)
                }
              }}
              className={cn(
                'group relative rounded-md border p-2 text-left transition-all',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background',
                selected
                  ? 'border-primary/60 bg-primary/10 shadow-sm'
                  : cn('bg-muted/15 hover:bg-muted/25', STATUS_RING[tone]),
                disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
              )}
            >
              <div className="flex items-start gap-1.5">
                <div
                  className={cn(
                    'mt-px flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors',
                    selected
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-muted-foreground/40 bg-background/50',
                  )}
                >
                  {selected && <Check size={10} strokeWidth={3} />}
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-1">
                    <div
                      id={`${inputId}-title`}
                      className="truncate text-[13px] font-semibold leading-tight"
                    >
                      {provider.name}
                    </div>
                    {cidrCount != null && cidrCount > 0 ? (
                      <span className="shrink-0 font-mono text-[11px] font-semibold tabular-nums text-muted-foreground">
                        {formatCompactCount(cidrCount)}
                      </span>
                    ) : (
                      <Badge variant="outline" className="h-4 shrink-0 px-1 text-[9px]">
                        —
                      </Badge>
                    )}
                  </div>

                  <div className="mt-0.5 flex items-center justify-between gap-1">
                    <div className="flex min-w-0 items-center gap-1">
                      <span
                        className={cn('h-1.5 w-1.5 shrink-0 rounded-full', STATUS_DOT[tone])}
                        title={statusLabel(dbMeta?.refresh_status)}
                      />
                      <span className="truncate text-[10px] text-muted-foreground">
                        {providerCategoryLabel(provider.category)}
                        {dbMeta?.refresh_status && dbMeta.refresh_status !== 'never' && (
                          <> · {statusLabel(dbMeta.refresh_status)}</>
                        )}
                      </span>
                    </div>

                    {showQuickIngest && onRefreshOne && (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-5 w-5 shrink-0 p-0 opacity-70 hover:opacity-100"
                        disabled={disabled}
                        title="Загрузить только этого провайдера"
                        onClick={(e) => {
                          e.stopPropagation()
                          onRefreshOne(provider.filename)
                        }}
                      >
                        <CloudDownload size={11} />
                      </Button>
                    )}
                  </div>
                </div>
              </div>

              <input
                id={inputId}
                type="checkbox"
                checked={selected}
                disabled={disabled}
                onChange={() => toggleFile(provider.filename)}
                onClick={(e) => e.stopPropagation()}
                className="sr-only"
                aria-hidden
              />
            </div>
          )
        })}
      </div>

      {filtered.length === 0 && (
        <p className="text-center text-sm text-muted-foreground py-6">Ничего не найдено по фильтру</p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-muted/30 px-3 py-2 text-xs">
        <span className="text-muted-foreground">
          Выбрано{' '}
          <strong className="text-foreground font-semibold">{selectedFiles.length}</strong> из{' '}
          {providers.length}
          {selectedCidrTotal > 0 && (
            <>
              {' '}
              · в БД ~{' '}
              <strong className="text-foreground font-semibold tabular-nums">
                {selectedCidrTotal.toLocaleString('ru-RU')}
              </strong>{' '}
              CIDR
            </>
          )}
        </span>
        {selectedFiles.length === 0 ? (
          <Badge variant="destructive" className="text-[10px]">
            Нужен минимум 1 провайдер
          </Badge>
        ) : (
          <Badge variant={statusBadgeVariant('ok')} className="text-[10px]">
            Готово к запуску
          </Badge>
        )}
      </div>
    </div>
  )
}
