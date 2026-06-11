import { useMemo, useState } from 'react'
import { Route, Search, CloudDownload } from 'lucide-react'
import StatusPanel from '@/components/noc/StatusPanel'
import EmptyState from '@/components/ui/EmptyState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import type { CidrDbStatus, CidrProviderInfo, Node } from '@/types'
import { formatDt, formatCompactCount, providerCategoryLabel, providerSlug, statusBadgeVariant, statusLabel } from './utils'

interface ProvidersTabProps {
  providers: CidrProviderInfo[]
  cidrDb: CidrDbStatus | null
  activeNode: Node | null
  isAdmin: boolean
  actionLoading: boolean
  onToggle: (filename: string, enabled: boolean, name: string) => void
  onRefreshOne?: (filename: string) => void
  pipelineBusy?: boolean
}

function hasControllerArtifact(cidrDb: CidrDbStatus | null, filename: string): boolean {
  const artifact = cidrDb?.compile_artifacts?.[filename]
  return Boolean(artifact?.exists && (artifact.cidr_count ?? 0) > 0)
}

function controllerCidrCount(cidrDb: CidrDbStatus | null, filename: string): number | null {
  const artifact = cidrDb?.compile_artifacts?.[filename]
  if (!artifact?.exists) return null
  return artifact.cidr_count ?? 0
}

export default function ProvidersTab({
  providers,
  cidrDb,
  activeNode,
  isAdmin,
  actionLoading,
  onToggle,
  onRefreshOne,
  pipelineBusy = false,
}: ProvidersTabProps) {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [categoryFilter, setCategoryFilter] = useState('all')

  const categories = useMemo(
    () => [...new Set(providers.map((p) => p.category))].sort(),
    [providers],
  )

  const needsCompile = useMemo(
    () =>
      providers.some((p) => {
        const dbMeta = cidrDb?.providers?.[p.filename]
        const hasDb =
          (dbMeta?.cidr_count ?? 0) > 0 &&
          (dbMeta?.refresh_status === 'ok' || dbMeta?.refresh_status === 'partial')
        return hasDb && !hasControllerArtifact(cidrDb, p.filename)
      }),
    [providers, cidrDb],
  )

  const needsDeploy = useMemo(
    () =>
      providers.some((p) => {
        const dbMeta = cidrDb?.providers?.[p.filename]
        const hasDb =
          (dbMeta?.cidr_count ?? 0) > 0 &&
          (dbMeta?.refresh_status === 'ok' || dbMeta?.refresh_status === 'partial')
        return hasDb && hasControllerArtifact(cidrDb, p.filename) && !p.has_source
      }),
    [providers, cidrDb],
  )

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return providers.filter((p) => {
      const dbMeta = cidrDb?.providers?.[p.filename]
      const dbStatus = dbMeta?.refresh_status ?? 'never'
      if (statusFilter !== 'all' && dbStatus !== statusFilter) return false
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
  }, [providers, cidrDb, search, statusFilter, categoryFilter])

  if (providers.length === 0) {
    return (
      <EmptyState
        icon={Search}
        title="Нет провайдеров"
        description="Список CIDR-провайдеров пуст. Проверьте конфигурацию AntiZapret."
      />
    )
  }

  const nodeLabel = activeNode?.name ?? 'активной ноде'

  return (
    <StatusPanel title="CIDR-провайдеры" icon={Route}>
      <div className="space-y-4">
        {needsCompile && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-950 dark:text-amber-100">
            Данные провайдеров уже в БД (этап 1), но файлы списков ещё не собраны на контроллере.
            Сначала выполните <strong>Этап 2 — Сборка списков</strong> на вкладке «Pipeline».
          </div>
        )}
        {needsDeploy && !needsCompile && (
          <div className="rounded-md border border-sky-500/40 bg-sky-500/10 px-4 py-3 text-sm text-sky-950 dark:text-sky-100">
            Списки собраны на контроллере. Выполните <strong>Этап 3 — Deploy</strong> на вкладке
            «Pipeline» для ноды <strong>{nodeLabel}</strong>, затем включите нужных провайдеров для
            маршрутизации AntiZapret.
          </div>
        )}
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Поиск по имени или категории…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder="Статус БД" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Все статусы</SelectItem>
              <SelectItem value="ok">OK</SelectItem>
              <SelectItem value="partial">Частично</SelectItem>
              <SelectItem value="error">Ошибка</SelectItem>
              <SelectItem value="never">Нет данных</SelectItem>
            </SelectContent>
          </Select>
          <Select value={categoryFilter} onValueChange={setCategoryFilter}>
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder="Категория" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Все категории</SelectItem>
              {categories.map((c) => (
                <SelectItem key={c} value={c}>
                  {providerCategoryLabel(c)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="text-xs text-muted-foreground">Показано: {filtered.length}</span>
        </div>

        <div className="rounded-md border overflow-hidden">
          <div className="max-h-[min(70vh,600px)] overflow-auto">
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-muted/95 backdrop-blur supports-[backdrop-filter]:bg-muted/80">
                <TableRow>
                  <TableHead>Провайдер</TableHead>
                  <TableHead>Категория</TableHead>
                  <TableHead className="text-right">CIDR (контроллер)</TableHead>
                  <TableHead className="text-right">CIDR (нода)</TableHead>
                  <TableHead className="text-right">CIDR (БД)</TableHead>
                  <TableHead>БД refresh</TableHead>
                  <TableHead>Статус</TableHead>
                  {isAdmin && (
                    <TableHead className="text-right">Действия</TableHead>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((p, idx) => {
                  const dbMeta = cidrDb?.providers?.[p.filename]
                  const onController = hasControllerArtifact(cidrDb, p.filename)
                  const enableBlocked = !p.has_source && !p.enabled
                  const rowHint = !p.has_source
                    ? onController
                      ? 'нет на ноде — нужен deploy'
                      : (dbMeta?.cidr_count ?? 0) > 0
                        ? 'нет файла — нужен этап 2'
                        : 'нет источника'
                    : null

                  return (
                    <TableRow
                      key={p.filename}
                      className={cn(idx % 2 === 1 && 'bg-muted/30')}
                    >
                      <TableCell title={`ID: ${providerSlug(p.filename)} · ${p.filename}`}>
                        <div className="font-medium">{p.name}</div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{providerCategoryLabel(p.category)}</Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {(() => {
                          const n = controllerCidrCount(cidrDb, p.filename)
                          return n != null ? formatCompactCount(n) : '—'
                        })()}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {formatCompactCount(p.cidr_count)}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {dbMeta?.cidr_count != null ? formatCompactCount(dbMeta.cidr_count) : '—'}
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusBadgeVariant(dbMeta?.refresh_status)}>
                          {statusLabel(dbMeta?.refresh_status)}
                        </Badge>
                        <div className="text-xs text-muted-foreground mt-1">
                          {formatDt(dbMeta?.last_refreshed_at)}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={p.enabled ? 'default' : 'secondary'}>
                          {p.enabled ? 'Включён' : 'Выключен'}
                        </Badge>
                        {rowHint && (
                          <span className="ml-2 text-xs text-amber-600 dark:text-amber-400">
                            {rowHint}
                          </span>
                        )}
                      </TableCell>
                      {isAdmin && (
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-2">
                            {onRefreshOne && (
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={actionLoading || pipelineBusy}
                                title="Обновить только этого провайдера из интернета"
                                onClick={() => onRefreshOne(p.filename)}
                              >
                                <CloudDownload size={14} className="mr-1" />
                                Загрузить
                              </Button>
                            )}
                            <Button
                              size="sm"
                              variant={p.enabled ? 'outline' : 'default'}
                              disabled={actionLoading || enableBlocked}
                              title={
                                enableBlocked && onController
                                  ? 'Сначала выполните Deploy на активную ноду'
                                  : enableBlocked
                                    ? 'Сначала соберите списки на контроллере (этап 2)'
                                    : undefined
                              }
                              onClick={() => onToggle(p.filename, !p.enabled, p.name)}
                            >
                              {p.enabled ? 'Отключить' : 'Включить'}
                            </Button>
                          </div>
                        </TableCell>
                      )}
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        </div>
      </div>
    </StatusPanel>
  )
}
