import { useCallback, useEffect, useState } from 'react'
import { Check, Download, Eye, Library, Plus, RefreshCw, Search, Trash2 } from 'lucide-react'
import {
  addWarperCatalog,
  getWarperCatalogInstalled,
  refreshWarperCatalog,
  removeWarperCatalog,
  searchWarperCatalog,
  showWarperCatalog,
  updateWarperCatalog,
} from '@/api/client'
import StatusPanel from '@/components/noc/StatusPanel'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import type {
  WarperCatalogItem,
  WarperCatalogShowResponse,
  WarperHealthResponse,
} from '@/types'
import { isWarperDisabled } from './utils'

interface CatalogTabProps {
  health: WarperHealthResponse | null
  onDomainsChange?: () => void
}

export default function CatalogTab({ health, onDomainsChange }: CatalogTabProps) {
  const { activeNode } = useNode()
  const { success, error: notifyError } = useNotifications()
  const disabled = isWarperDisabled(health)

  const [query, setQuery] = useState('')
  const [results, setResults] = useState<WarperCatalogItem[]>([])
  const [installed, setInstalled] = useState<Set<string>>(new Set())
  const [installedList, setInstalledList] = useState<
    { name: string; domains_count?: number; updated_at?: string }[]
  >([])
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [busyName, setBusyName] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [preview, setPreview] = useState<WarperCatalogShowResponse | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  const runSearch = useCallback(
    async (q: string) => {
      if (!health?.installed) return
      setSearching(true)
      try {
        const data = await searchWarperCatalog(q)
        setResults(data.items ?? [])
      } catch (err) {
        notifyError(err instanceof Error ? err.message : 'Не удалось выполнить поиск каталога')
        setResults([])
      } finally {
        setSearching(false)
      }
    },
    [health?.installed, notifyError],
  )

  const loadInstalled = useCallback(async () => {
    if (!health?.installed) {
      setInstalled(new Set())
      setInstalledList([])
      return
    }
    try {
      const data = await getWarperCatalogInstalled()
      const items = data.items ?? []
      setInstalledList(items)
      setInstalled(new Set(items.map((item) => item.name)))
    } catch {
      setInstalled(new Set())
      setInstalledList([])
    }
  }, [health?.installed])

  const load = useCallback(async () => {
    if (!health?.installed) {
      setLoading(false)
      return
    }
    setLoading(true)
    await Promise.all([runSearch(''), loadInstalled()])
    setLoading(false)
  }, [health?.installed, runSearch, loadInstalled])

  useEffect(() => {
    void load()
  }, [load, activeNode?.id])

  async function handlePreview(name: string) {
    setPreviewLoading(true)
    setPreview({ name, count: 0, domains: [] })
    try {
      const data = await showWarperCatalog(name)
      setPreview(data)
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось загрузить предпросмотр')
      setPreview(null)
    } finally {
      setPreviewLoading(false)
    }
  }

  async function handleAdd(name: string) {
    setBusyName(name)
    try {
      const result = await addWarperCatalog(name)
      success(result.message ?? `Каталог «${name}» добавлен`)
      await loadInstalled()
      onDomainsChange?.()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось добавить каталог')
    } finally {
      setBusyName(null)
    }
  }

  async function handleRemove(name: string) {
    setBusyName(name)
    try {
      const result = await removeWarperCatalog(name)
      success(result.message ?? `Каталог «${name}» удалён`)
      await loadInstalled()
      onDomainsChange?.()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось удалить каталог')
    } finally {
      setBusyName(null)
    }
  }

  async function handleUpdate(name = '') {
    setBusyName(name || '__all__')
    try {
      const result = await updateWarperCatalog(name)
      success(result.message ?? (name ? `Каталог «${name}» обновлён` : 'Каталоги обновлены'))
      await loadInstalled()
      onDomainsChange?.()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось обновить каталог')
    } finally {
      setBusyName(null)
    }
  }

  async function handleRefreshCache() {
    setRefreshing(true)
    try {
      const result = await refreshWarperCatalog()
      success(result.message ?? 'Кэш каталога обновлён')
      await runSearch(query)
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось обновить кэш')
    } finally {
      setRefreshing(false)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner label="Загрузка каталога..." />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <StatusPanel title="Установленные каталоги" icon={Library}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">
            Готовые списки доменов из community-репозитория v2fly/domain-list-community.
          </p>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={disabled || busyName !== null || installedList.length === 0}
              onClick={() => void handleUpdate('')}
            >
              <RefreshCw className={`mr-1.5 h-4 w-4 ${busyName === '__all__' ? 'animate-spin' : ''}`} />
              Обновить все
            </Button>
          </div>
        </div>

        {installedList.length === 0 ? (
          <p className="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
            Каталоги не добавлены. Найдите нужный список ниже и нажмите «Добавить».
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {installedList.map((item) => (
              <div
                key={item.name}
                className="flex items-center gap-2 rounded-lg border bg-muted/20 py-1.5 pl-3 pr-1.5"
              >
                <span className="text-sm font-medium">{item.name}</span>
                {typeof item.domains_count === 'number' && (
                  <Badge variant="outline" className="text-xs">
                    {item.domains_count}
                  </Badge>
                )}
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  disabled={disabled || busyName !== null}
                  title="Обновить"
                  onClick={() => void handleUpdate(item.name)}
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${busyName === item.name ? 'animate-spin' : ''}`} />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-destructive hover:text-destructive"
                  disabled={disabled || busyName !== null}
                  title="Удалить"
                  onClick={() => void handleRemove(item.name)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </StatusPanel>

      <StatusPanel title="Поиск каталогов" icon={Search}>
        <form
          className="mb-4 flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            void runSearch(query)
          }}
        >
          <Input
            placeholder="tiktok, netflix, telegram, openai…"
            value={query}
            disabled={!health?.installed}
            onChange={(e) => setQuery(e.target.value)}
            className="max-w-xs"
          />
          <Button type="submit" disabled={!health?.installed || searching}>
            <Search className="mr-1.5 h-4 w-4" />
            Найти
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={!health?.installed || refreshing}
            onClick={() => void handleRefreshCache()}
            title="Обновить кэш категорий с GitHub"
          >
            <RefreshCw className={`mr-1.5 h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            Обновить кэш
          </Button>
        </form>

        {searching ? (
          <div className="flex justify-center py-8">
            <Spinner />
          </div>
        ) : results.length === 0 ? (
          <EmptyState
            icon={Library}
            title="Ничего не найдено"
            description="Измените запрос или обновите кэш категорий."
            className="py-8"
          />
        ) : (
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {results.map((item) => {
              const isInstalled = installed.has(item.name) || Boolean(item.installed)
              const busy = busyName === item.name
              return (
                <div
                  key={item.name}
                  className="flex items-center justify-between gap-2 rounded-lg border bg-card/40 p-3"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="truncate text-sm font-medium">{item.name}</span>
                    {item.popular && (
                      <Badge variant="secondary" className="text-[10px]">
                        популярный
                      </Badge>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      title="Предпросмотр"
                      onClick={() => void handlePreview(item.name)}
                    >
                      <Eye className="h-4 w-4" />
                    </Button>
                    {isInstalled ? (
                      <Badge variant="success" className="gap-1">
                        <Check className="h-3 w-3" />
                        Добавлен
                      </Badge>
                    ) : (
                      <Button
                        size="sm"
                        disabled={disabled || busyName !== null}
                        onClick={() => void handleAdd(item.name)}
                      >
                        {busy ? (
                          <RefreshCw className="mr-1.5 h-4 w-4 animate-spin" />
                        ) : (
                          <Plus className="mr-1.5 h-4 w-4" />
                        )}
                        Добавить
                      </Button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </StatusPanel>

      <Dialog open={preview !== null} onOpenChange={(open) => !open && setPreview(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Library className="h-4 w-4" />
              {preview?.name}
            </DialogTitle>
            <DialogDescription>
              {previewLoading
                ? 'Загрузка доменов…'
                : `${preview?.count ?? preview?.domains.length ?? 0} доменов в категории`}
            </DialogDescription>
          </DialogHeader>
          {previewLoading ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : (
            <div className="max-h-72 overflow-y-auto rounded-lg border bg-muted/20 p-3">
              <ul className="space-y-0.5 font-mono text-xs">
                {(preview?.domains ?? []).map((domain) => (
                  <li key={domain} className="truncate">
                    {domain}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {preview && !previewLoading && !installed.has(preview.name) && (
            <Button
              className="w-full"
              disabled={disabled || busyName !== null}
              onClick={() => {
                const name = preview.name
                setPreview(null)
                void handleAdd(name)
              }}
            >
              <Download className="mr-1.5 h-4 w-4" />
              Добавить «{preview.name}»
            </Button>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
