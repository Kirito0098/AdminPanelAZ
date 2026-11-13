import { useMemo, useState } from 'react'
import { CloudDownload } from 'lucide-react'
import ProviderFilterBar from '@/components/routing/ProviderFilterBar'
import { filterProviders } from '@/components/routing/providerFilters'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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

/** Фиксированный набор чипов категорий — как в фильтре до объединения. */
const CATEGORY_CHIPS = ['cdn', 'cloud', 'hosting'] as const

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
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('all')

  const selectedSet = new Set(selectedFiles)
  const allFilenames = providers.map((p) => p.filename)

  const toggleFile = (filename: string) => {
    if (selectedSet.has(filename)) {
      onSelectedFilesChange(selectedFiles.filter((f) => f !== filename))
    } else {
      onSelectedFilesChange([...new Set([...selectedFiles, filename])])
    }
  }

  // Действия ниже работают по полному набору провайдеров, а не по отфильтрованному:
  // «Все (N)» и «Ошибки (N)» показывают те же числа, что и выбирают.
  const selectAll = () => onSelectedFilesChange([...allFilenames])
  const selectNone = () => onSelectedFilesChange([])
  const selectFailed = () => {
    const failed = providers
      .filter((p) => cidrDb?.providers?.[p.filename]?.refresh_status === 'error')
      .map((p) => p.filename)
    onSelectedFilesChange(failed)
  }

  const selectByCategory = (target: string) => {
    if (target === 'all') {
      selectAll()
      return
    }
    onSelectedFilesChange(providers.filter((p) => p.category === target).map((p) => p.filename))
  }

  const failedCount = providers.filter(
    (p) => cidrDb?.providers?.[p.filename]?.refresh_status === 'error',
  ).length

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const provider of providers) {
      counts[provider.category] = (counts[provider.category] ?? 0) + 1
    }
    return counts
  }, [providers])

  const filtered = useMemo(
    () =>
      filterProviders(providers, {
        query,
        category,
        tagsOf: (provider) => cidrDb?.providers?.[provider.filename]?.tags,
      }),
    [providers, cidrDb, query, category],
  )

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
            Отметьте одного или нескольких — необязательно обновлять все {providers.length}. Технический ID скрыт;
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

      <ProviderFilterBar
        query={query}
        onQueryChange={setQuery}
        category={category}
        onCategoryChange={setCategory}
        categories={CATEGORY_CHIPS}
        categoryCounts={categoryCounts}
        resultCount={filtered.length}
        totalCount={providers.length}
        disabled={disabled}
        placeholder="Поиск: Akamai, cloud, hosting…"
        extra={
          category !== 'all' ? (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-7 px-2 text-xs"
              disabled={disabled}
              title={`Выбрать только категорию «${providerCategoryLabel(category)}»`}
              aria-label={`Выбрать только категорию «${providerCategoryLabel(category)}»`}
              onClick={() => selectByCategory(category)}
            >
              Только «{providerCategoryLabel(category)}»
            </Button>
          ) : undefined
        }
      />

      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
        {filtered.map((provider) => {
          const dbMeta = cidrDb?.providers?.[provider.filename]
          const selected = selectedSet.has(provider.filename)
          const checkboxId = `${idPrefix}-${provider.filename}`
          const slug = providerSlug(provider.filename)
          const tone = providerStatusTone(dbMeta?.refresh_status)
          const cidrCount = dbMeta?.cidr_count
          const quickIngestVisible = showQuickIngest && Boolean(onRefreshOne)

          return (
            <div
              key={provider.filename}
              title={`ID: ${slug} · файл списка: ${provider.filename}`}
              className={cn(
                'group relative rounded-md border transition-all',
                selected
                  ? 'border-primary/60 bg-primary/10 shadow-sm'
                  : cn('bg-muted/15 hover:bg-muted/25', STATUS_RING[tone]),
                disabled && 'opacity-60',
              )}
            >
              <label
                htmlFor={checkboxId}
                className={cn(
                  'flex items-start gap-1.5 rounded-md p-2',
                  disabled ? 'cursor-not-allowed' : 'cursor-pointer',
                )}
              >
                <input
                  id={checkboxId}
                  type="checkbox"
                  checked={selected}
                  disabled={disabled}
                  aria-label={provider.name}
                  onChange={() => toggleFile(provider.filename)}
                  className="mt-px h-4 w-4 shrink-0 cursor-pointer accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed"
                />

                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline justify-between gap-1">
                    <span
                      className="truncate text-[13px] font-semibold leading-tight"
                    >
                      {provider.name}
                    </span>
                    {cidrCount != null && cidrCount > 0 ? (
                      <span className="shrink-0 font-mono text-[11px] font-semibold tabular-nums text-muted-foreground">
                        {formatCompactCount(cidrCount)}
                      </span>
                    ) : (
                      <Badge variant="outline" className="h-4 shrink-0 px-1 text-[9px]">
                        —
                      </Badge>
                    )}
                  </span>

                  <span
                    className={cn(
                      'mt-0.5 flex items-center justify-between gap-1',
                      quickIngestVisible && 'pr-5',
                    )}
                  >
                    <span className="flex min-w-0 items-center gap-1">
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
                    </span>
                  </span>
                </span>
              </label>

              {quickIngestVisible && onRefreshOne && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="absolute bottom-1 right-1 h-5 w-5 shrink-0 p-0 opacity-70 hover:opacity-100"
                  disabled={disabled}
                  title="Загрузить только этого провайдера"
                  aria-label={`Загрузить только провайдера ${provider.name}`}
                  onClick={() => onRefreshOne(provider.filename)}
                >
                  <CloudDownload size={11} />
                </Button>
              )}
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
