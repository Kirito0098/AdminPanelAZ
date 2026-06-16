import { useMemo, useState } from 'react'
import { Route, Search, Pencil } from 'lucide-react'
import ProviderEditorDialog from '@/components/routing/ProviderEditorDialog'
import type { RoutingTab, RoutingWorkflowState } from '@/components/routing/routingWorkflow'
import { hasControllerArtifact, providerNeedsCompile, providerNeedsDeploy } from '@/components/routing/routingWorkflow'
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
import { formatDt, formatCompactCount, pluralProviders, providerCategoryLabel, providerSlug, statusBadgeVariant, statusLabel } from './utils'

interface ProvidersTabProps {
  providers: CidrProviderInfo[]
  cidrDb: CidrDbStatus | null
  activeNode: Node | null
  isAdmin: boolean
  actionLoading: boolean
  onToggle: (filename: string, enabled: boolean, name: string) => void
  pipelineBusy?: boolean
  onNavigateTab?: (tab: RoutingTab, anchor?: string) => void
  workflow?: RoutingWorkflowState
}

type QuickFilter = 'all' | 'enabled' | 'disabled' | 'errors' | 'needs_deploy' | 'needs_compile'

function controllerCidrCount(cidrDb: CidrDbStatus | null, filename: string): number | null {
  const artifact = cidrDb?.compile_artifacts?.[filename]
  if (!artifact?.exists) return null
  return artifact.cidr_count ?? 0
}

function dbCidrCount(cidrDb: CidrDbStatus | null, filename: string): number | null {
  const dbMeta = cidrDb?.providers?.[filename]
  if (dbMeta?.cidr_count == null) return null
  return dbMeta.cidr_count
}

function CidrCountsCell({
  cidrDb,
  provider,
}: {
  cidrDb: CidrDbStatus | null
  provider: CidrProviderInfo
}) {
  const db = dbCidrCount(cidrDb, provider.filename)
  const controller = controllerCidrCount(cidrDb, provider.filename)
  const node = provider.has_source ? provider.cidr_count : null

  return (
    <div className="space-y-1 text-right font-mono tabular-nums text-xs">
      <div className="flex items-center justify-end gap-1.5">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground w-8">БД</span>
        <span>{db != null ? formatCompactCount(db) : '—'}</span>
      </div>
      <div className="flex items-center justify-end gap-1.5">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground w-8">Контр.</span>
        <span>{controller != null ? formatCompactCount(controller) : '—'}</span>
      </div>
      <div className="flex items-center justify-end gap-1.5">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground w-8">Узел</span>
        <span>{node != null ? formatCompactCount(node) : '—'}</span>
      </div>
    </div>
  )
}

export default function ProvidersTab({
  providers,
  cidrDb,
  activeNode,
  isAdmin,
  actionLoading,
  onToggle,
  pipelineBusy = false,
  onNavigateTab,
  workflow,
}: ProvidersTabProps) {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [quickFilter, setQuickFilter] = useState<QuickFilter>('all')
  const [editorFilename, setEditorFilename] = useState<string | null>(null)
  const [editorName, setEditorName] = useState('')

  const categories = useMemo(
    () => [...new Set(providers.map((p) => p.category))].sort(),
    [providers],
  )

  const needsCompile = (workflow?.pendingCompileCount ?? 0) > 0
  const needsDeploy = (workflow?.pendingDeployCount ?? 0) > 0

  const quickFilterCounts = useMemo(() => {
    let enabled = 0
    let disabled = 0
    let errors = 0
    let needsDeployCount = 0
    let needsCompileCount = 0
    for (const p of providers) {
      const dbMeta = cidrDb?.providers?.[p.filename]
      if (p.enabled) enabled++
      else disabled++
      if (dbMeta?.refresh_status === 'error') errors++
      if (providerNeedsCompile(cidrDb, p)) needsCompileCount++
      if (providerNeedsDeploy(cidrDb, p)) needsDeployCount++
    }
    return { enabled, disabled, errors, needsDeployCount, needsCompileCount }
  }, [providers, cidrDb])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return providers.filter((p) => {
      const dbMeta = cidrDb?.providers?.[p.filename]
      const dbStatus = dbMeta?.refresh_status ?? 'never'

      if (statusFilter !== 'all' && dbStatus !== statusFilter) return false
      if (categoryFilter !== 'all' && p.category !== categoryFilter) return false

      if (quickFilter === 'enabled' && !p.enabled) return false
      if (quickFilter === 'disabled' && p.enabled) return false
      if (quickFilter === 'errors' && dbStatus !== 'error') return false
      if (quickFilter === 'needs_deploy' && !providerNeedsDeploy(cidrDb, p)) return false
      if (quickFilter === 'needs_compile' && !providerNeedsCompile(cidrDb, p)) return false

      if (!q) return true
      const slug = providerSlug(p.filename)
      return (
        p.name.toLowerCase().includes(q) ||
        slug.includes(q) ||
        p.category.toLowerCase().includes(q) ||
        providerCategoryLabel(p.category).toLowerCase().includes(q)
      )
    })
  }, [providers, cidrDb, search, statusFilter, categoryFilter, quickFilter])

  if (providers.length === 0) {
    return (
      <EmptyState
        icon={Search}
        title="Нет провайдеров"
        description="Список CIDR-провайдеров пуст. Проверьте конфигурацию AntiZapret."
      />
    )
  }

  const nodeLabel = activeNode?.name ?? 'активном узле'

  const quickFilters: Array<{ id: QuickFilter; label: string; count?: number }> = [
    { id: 'all', label: 'Все', count: providers.length },
    { id: 'enabled', label: 'Включённые', count: quickFilterCounts.enabled },
    { id: 'disabled', label: 'Выключенные', count: quickFilterCounts.disabled },
    { id: 'errors', label: 'Ошибки', count: quickFilterCounts.errors },
    { id: 'needs_deploy', label: 'Нужен deploy', count: quickFilterCounts.needsDeployCount },
    { id: 'needs_compile', label: 'Нужна сборка', count: quickFilterCounts.needsCompileCount },
  ]

  return (
    <>
      <StatusPanel title="CIDR-провайдеры" icon={Route}>
        <div className="space-y-4">
          {needsCompile && isAdmin && !workflow?.optionalCompileRemaining && (
            <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-950 dark:text-amber-100">
              Данные провайдеров уже в БД (этап 1), но файлы списков ещё не собраны на контроллере.{' '}
              {onNavigateTab ? (
                <button
                  type="button"
                  className="font-medium underline underline-offset-2 hover:text-amber-700 dark:hover:text-amber-50"
                  onClick={() => onNavigateTab('pipeline', 'pipeline-stage-2')}
                >
                  Перейти к этапу 2 — Сборка списков
                </button>
              ) : (
                <>
                  Сначала выполните <strong>Этап 2 — Сборка списков</strong> на вкладке «Pipeline».
                </>
              )}
            </div>
          )}
          {needsCompile && isAdmin && workflow?.optionalCompileRemaining && (
            <div className="rounded-md border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm text-amber-900 dark:text-amber-100">
              Сборка завершена.{' '}
              {workflow.pendingCompileNames.length === 1 ? (
                <>
                  У «{workflow.pendingCompileNames[0]}» нет файла на контроллере — можно пропустить или{' '}
                </>
              ) : (
                <>
                  {pluralProviders(workflow.pendingCompileCount)} без файла — необязательно, или{' '}
                </>
              )}
              {onNavigateTab ? (
                <button
                  type="button"
                  className="font-medium underline underline-offset-2"
                  onClick={() => onNavigateTab('pipeline', 'pipeline-stage-2')}
                >
                  собрать отдельно
                </button>
              ) : (
                'собрать на этапе 2'
              )}
              . Следующий шаг —{' '}
              {onNavigateTab ? (
                <button
                  type="button"
                  className="font-medium underline underline-offset-2"
                  onClick={() => onNavigateTab('pipeline', 'pipeline-stage-3')}
                >
                  Deploy на узел
                </button>
              ) : (
                'Deploy на узел'
              )}
              .
            </div>
          )}
          {needsDeploy && !needsCompile && isAdmin && (
            <div className="rounded-md border border-sky-500/40 bg-sky-500/10 px-4 py-3 text-sm text-sky-950 dark:text-sky-100">
              Списки собраны на контроллере.{' '}
              {onNavigateTab ? (
                <>
                  <button
                    type="button"
                    className="font-medium underline underline-offset-2 hover:text-sky-700 dark:hover:text-sky-50"
                    onClick={() => onNavigateTab('pipeline', 'pipeline-stage-3')}
                  >
                    Выполните Deploy
                  </button>{' '}
                  для узла <strong>{nodeLabel}</strong>, затем включите нужных провайдеров.
                </>
              ) : (
                <>
                  Выполните <strong>Этап 3 — Deploy</strong> на вкладке «Pipeline» для узла{' '}
                  <strong>{nodeLabel}</strong>.
                </>
              )}
            </div>
          )}

          <div className="flex flex-wrap gap-1.5">
            {quickFilters.map((item) => {
              if (item.id !== 'all' && item.count === 0) return null
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setQuickFilter(item.id)}
                  className={cn(
                    'rounded-full border px-2.5 py-1 text-xs transition-colors',
                    quickFilter === item.id
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-transparent bg-muted/60 text-muted-foreground hover:bg-muted',
                  )}
                >
                  {item.label}
                  {item.count != null && item.id !== 'all' && (
                    <span className="ml-1 opacity-70">({item.count})</span>
                  )}
                </button>
              )
            })}
          </div>

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

          <p className="text-[11px] text-muted-foreground">
            CIDR: <strong>БД</strong> — SQLite на контроллере · <strong>Контр.</strong> — собранный
            файл · <strong>Узел</strong> — файл на VPN-сервере
          </p>

          <div className="rounded-md border overflow-hidden">
            <div className="max-h-[min(70vh,600px)] overflow-auto">
              <Table>
                <TableHeader className="sticky top-0 z-10 bg-muted/95 backdrop-blur supports-[backdrop-filter]:bg-muted/80">
                  <TableRow>
                    <TableHead className="min-w-[140px]">Провайдер</TableHead>
                    <TableHead>Категория</TableHead>
                    <TableHead className="text-right min-w-[100px]">CIDR</TableHead>
                    <TableHead>БД refresh</TableHead>
                    <TableHead>Маршрутизация</TableHead>
                    {isAdmin && <TableHead className="text-right min-w-[160px]">Действия</TableHead>}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.length === 0 ? (
                    <TableRow>
                      <TableCell
                        colSpan={isAdmin ? 6 : 5}
                        className="h-24 text-center text-sm text-muted-foreground"
                      >
                        Нет провайдеров по выбранным фильтрам
                      </TableCell>
                    </TableRow>
                  ) : (
                    filtered.map((p, idx) => {
                      const dbMeta = cidrDb?.providers?.[p.filename]
                      const onController = hasControllerArtifact(cidrDb, p.filename)
                      const enableBlocked = !p.has_source && !p.enabled
                      const rowHint = !p.has_source
                        ? onController
                          ? 'нет на узле — deploy'
                          : (dbMeta?.cidr_count ?? 0) > 0
                            ? 'нет файла — сборка'
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
                          <TableCell>
                            <CidrCountsCell cidrDb={cidrDb} provider={p} />
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
                                <Button
                                  size="sm"
                                  variant="outline"
                                  disabled={actionLoading || pipelineBusy}
                                  title="Редактировать файл списка провайдера на узле"
                                  onClick={() => {
                                    setEditorFilename(p.filename)
                                    setEditorName(p.name)
                                  }}
                                >
                                  <Pencil size={14} className="mr-1" />
                                  Редактировать
                                </Button>
                                <Button
                                  size="sm"
                                  variant={p.enabled ? 'outline' : 'default'}
                                  disabled={actionLoading || enableBlocked}
                                  title={
                                    enableBlocked && onController
                                      ? 'Сначала выполните Deploy на активный узел'
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
                    })
                  )}
                </TableBody>
              </Table>
            </div>
          </div>
        </div>
      </StatusPanel>

      <ProviderEditorDialog
        filename={editorFilename}
        providerName={editorName}
        open={editorFilename != null}
        onOpenChange={(open) => {
          if (!open) setEditorFilename(null)
        }}
      />
    </>
  )
}
