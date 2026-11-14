import { useMemo, useState } from 'react'
import { Route, Search, Pencil, Play } from 'lucide-react'
import ProviderEditorDialog from '@/components/routing/ProviderEditorDialog'
import ProviderFilterBar, { type ProviderFilterStatusOption } from '@/components/routing/ProviderFilterBar'
import { filterProviders, type ProviderQuickFilter } from '@/components/routing/providerFilters'
import { ROUTING_TAB_UPDATE, STAGE_BUILD, STAGE_DEPLOY } from '@/components/routing/routingLabels'
import type { RoutingTab, RoutingWorkflowState } from '@/components/routing/routingWorkflow'
import { hasControllerArtifact, providerNeedsCompile, providerNeedsDeploy } from '@/components/routing/routingWorkflow'
import StatusPanel from '@/components/noc/StatusPanel'
import EmptyState from '@/components/ui/EmptyState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import type { CidrDbStatus, CidrProviderInfo, Node } from '@/types'
import { formatDt, formatCompactCount, pluralProviders, providerCategoryLabel, providerSlug, statusBadgeVariant, statusLabel } from './utils'

interface ProvidersTabProps {
  providers: CidrProviderInfo[]
  cidrDb: CidrDbStatus | null
  activeNode: Node | null
  /** HA replica: маршрутизация только для чтения, действия недоступны. */
  readonly?: boolean
  actionLoading: boolean
  onToggle: (filename: string, enabled: boolean, name: string) => void
  pipelineBusy?: boolean
  onNavigateTab?: (tab: RoutingTab, anchor?: string) => void
  onApplyRouting?: () => void
  workflow?: RoutingWorkflowState
}

const STATUS_OPTIONS: readonly ProviderFilterStatusOption[] = [
  { value: 'all', label: 'Все статусы' },
  { value: 'ok', label: 'OK' },
  { value: 'partial', label: 'Частично' },
  { value: 'error', label: 'Ошибка' },
  { value: 'never', label: 'Нет данных' },
]

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

function CidrCountsGrid({
  cidrDb,
  provider,
}: {
  cidrDb: CidrDbStatus | null
  provider: CidrProviderInfo
}) {
  const db = dbCidrCount(cidrDb, provider.filename)
  const controller = controllerCidrCount(cidrDb, provider.filename)
  const node = provider.has_source ? provider.cidr_count : null

  const items = [
    { label: 'БД', value: db },
    { label: 'Контр.', value: controller },
    { label: 'Узел', value: node },
  ]

  return (
    <div className="grid grid-cols-3 divide-x divide-border rounded-md border bg-muted/20">
      {items.map(({ label, value }) => (
        <div key={label} className="px-2 py-1.5 text-center">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
          <div className="font-mono text-xs tabular-nums text-foreground">
            {value != null ? formatCompactCount(value) : '—'}
          </div>
        </div>
      ))}
    </div>
  )
}

interface ProviderListItemProps {
  provider: CidrProviderInfo
  cidrDb: CidrDbStatus | null
  readonly: boolean
  actionLoading: boolean
  pipelineBusy: boolean
  onToggle: (filename: string, enabled: boolean, name: string) => void
  onEdit: (filename: string, name: string) => void
}

function ProviderListItem({
  provider: p,
  cidrDb,
  readonly,
  actionLoading,
  pipelineBusy,
  onToggle,
  onEdit,
}: ProviderListItemProps) {
  const dbMeta = cidrDb?.providers?.[p.filename]
  const onController = hasControllerArtifact(cidrDb, p.filename)
  const enableBlocked = !p.has_source && !p.enabled
  const toggleDisabled = readonly || actionLoading || enableBlocked
  const switchId = `provider-enabled-${providerSlug(p.filename)}`
  const rowHint = !p.has_source
    ? onController
      ? 'нет на узле — нужно развёртывание'
      : (dbMeta?.cidr_count ?? 0) > 0
        ? 'нет файла — сборка'
        : 'нет источника'
    : null
  const toggleTitle =
    enableBlocked && onController
      ? `Сначала выполните ${STAGE_DEPLOY.toLowerCase()} на активный узел`
      : enableBlocked
        ? 'Сначала соберите списки на контроллере (этап 2)'
        : p.enabled
          ? 'Выключить провайдера'
          : 'Включить провайдера'

  return (
    <article
      className={cn(
        'flex flex-col gap-2 rounded-lg border px-3 py-2.5 transition-colors',
        p.enabled
          ? 'border-emerald-500/35 bg-emerald-500/[0.06]'
          : 'border-border/70 bg-muted/15 opacity-85',
      )}
      title={`ID: ${providerSlug(p.filename)} · ${p.filename}`}
    >
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            <h3
              className={cn(
                'truncate text-sm font-medium',
                !p.enabled && 'text-muted-foreground',
              )}
            >
              {p.name}
            </h3>
            <Badge variant="outline" className="shrink-0 px-1.5 py-0 text-[10px] font-normal">
              {providerCategoryLabel(p.category)}
            </Badge>
          </div>
        </div>
        <Label htmlFor={switchId} className="sr-only">
          {p.enabled ? 'Включён' : 'Выключен'}
        </Label>
        <Switch
          id={switchId}
          checked={p.enabled}
          disabled={toggleDisabled}
          title={toggleTitle}
          aria-label={`${p.name}: ${p.enabled ? 'включён' : 'выключен'}`}
          className={p.enabled ? 'bg-emerald-600' : undefined}
          onCheckedChange={(next) => {
            if (readonly || next === p.enabled) return
            onToggle(p.filename, next, p.name)
          }}
        />
        {!readonly && (
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 shrink-0 p-0 text-muted-foreground hover:text-foreground"
            disabled={actionLoading || pipelineBusy}
            title="Редактировать файл на узле"
            aria-label={`Редактировать ${p.name}`}
            onClick={() => onEdit(p.filename, p.name)}
          >
            <Pencil size={13} />
          </Button>
        )}
      </div>

      <CidrCountsGrid cidrDb={cidrDb} provider={p} />

      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted-foreground">
        <Badge variant={statusBadgeVariant(dbMeta?.refresh_status)} className="text-[10px]">
          {statusLabel(dbMeta?.refresh_status)}
        </Badge>
        <span>{formatDt(dbMeta?.last_refreshed_at)}</span>
        {rowHint && <span className="text-amber-600 dark:text-amber-400">{rowHint}</span>}
      </div>
    </article>
  )
}

export default function ProvidersTab({
  providers,
  cidrDb,
  activeNode,
  readonly = false,
  actionLoading,
  onToggle,
  pipelineBusy = false,
  onNavigateTab,
  onApplyRouting,
  workflow,
}: ProvidersTabProps) {
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [quickFilter, setQuickFilter] = useState<ProviderQuickFilter>('all')
  const [editorFilename, setEditorFilename] = useState<string | null>(null)
  const [editorName, setEditorName] = useState('')

  const categories = useMemo(
    () => [...new Set(providers.map((p) => p.category))].sort(),
    [providers],
  )

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const provider of providers) {
      counts[provider.category] = (counts[provider.category] ?? 0) + 1
    }
    return counts
  }, [providers])

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

  const filtered = useMemo(
    () =>
      filterProviders(providers, {
        query,
        category: categoryFilter,
        status: statusFilter,
        quickFilter,
        statusOf: (provider) => cidrDb?.providers?.[provider.filename]?.refresh_status,
        tagsOf: (provider) => cidrDb?.providers?.[provider.filename]?.tags,
        needsCompile: (provider) => providerNeedsCompile(cidrDb, provider),
        needsDeploy: (provider) => providerNeedsDeploy(cidrDb, provider),
      }),
    [providers, cidrDb, query, statusFilter, categoryFilter, quickFilter],
  )

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
  const onNodeCount = workflow?.onNodeCount ?? providers.filter((p) => p.has_source).length
  const enabledCount = workflow?.enabledCount ?? providers.filter((p) => p.enabled).length
  const showApplySection = !readonly && onNodeCount > 0 && !needsDeploy

  const quickFilters: Array<{ id: ProviderQuickFilter; label: string; count?: number }> = [
    { id: 'all', label: 'Все', count: providers.length },
    { id: 'enabled', label: 'Включённые', count: quickFilterCounts.enabled },
    { id: 'disabled', label: 'Выключенные', count: quickFilterCounts.disabled },
    { id: 'errors', label: 'Ошибки', count: quickFilterCounts.errors },
    { id: 'needs_deploy', label: `Нужно ${STAGE_DEPLOY.toLowerCase()}`, count: quickFilterCounts.needsDeployCount },
    { id: 'needs_compile', label: `Нужна ${STAGE_BUILD.toLowerCase()}`, count: quickFilterCounts.needsCompileCount },
  ]

  return (
    <>
      <StatusPanel title="CIDR-провайдеры" icon={Route}>
        <div className="space-y-4">
          {needsCompile && !readonly && !workflow?.optionalCompileRemaining && (
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
                  Сначала выполните <strong>Этап 2 — {STAGE_BUILD} списков</strong> на вкладке «{ROUTING_TAB_UPDATE}».
                </>
              )}
            </div>
          )}
          {needsCompile && !readonly && workflow?.optionalCompileRemaining && (
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
                  {STAGE_DEPLOY} на узел
                </button>
              ) : (
                `${STAGE_DEPLOY} на узел`
              )}
              .
            </div>
          )}
          {needsDeploy && !needsCompile && !readonly && (
            <div className="rounded-md border border-sky-500/40 bg-sky-500/10 px-4 py-3 text-sm text-sky-950 dark:text-sky-100">
              Списки собраны на контроллере.{' '}
              {onNavigateTab ? (
                <>
                  <button
                    type="button"
                    className="font-medium underline underline-offset-2 hover:text-sky-700 dark:hover:text-sky-50"
                    onClick={() => onNavigateTab('pipeline', 'pipeline-stage-3')}
                  >
                    Выполните {STAGE_DEPLOY.toLowerCase()}
                  </button>{' '}
                  для узла <strong>{nodeLabel}</strong>, затем включите нужных провайдеров.
                </>
              ) : (
                <>
                  Выполните <strong>Этап 3 — {STAGE_DEPLOY}</strong> на вкладке «{ROUTING_TAB_UPDATE}» для узла{' '}
                  <strong>{nodeLabel}</strong>.
                </>
              )}
            </div>
          )}

          {showApplySection && (
            <div
              className={cn(
                'rounded-md border px-4 py-3 text-sm',
                enabledCount > 0
                  ? 'border-primary/40 bg-primary/5 text-foreground'
                  : 'border-emerald-500/40 bg-emerald-500/10 text-emerald-950 dark:text-emerald-100',
              )}
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  {enabledCount > 0 ? (
                    <>
                      <strong>{enabledCount}</strong> {enabledCount === 1 ? 'провайдер включён' : 'провайдеров включено'}.
                      Примените doall, чтобы активировать маршруты с новыми CIDR на узле{' '}
                      <strong>{nodeLabel}</strong>.
                    </>
                  ) : (
                    <>
                      Файлы списков уже на узле <strong>{nodeLabel}</strong>. Включите нужных провайдеров
                      ниже — затем примените doall + client.sh 7.
                    </>
                  )}
                </div>
                {onApplyRouting && enabledCount > 0 && (
                  <Button
                    size="sm"
                    disabled={pipelineBusy || actionLoading}
                    onClick={onApplyRouting}
                    className="shrink-0"
                  >
                    <Play size={14} className="mr-1.5" />
                    Применить doall + client.sh 7
                  </Button>
                )}
              </div>
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

          <ProviderFilterBar
            query={query}
            onQueryChange={setQuery}
            category={categoryFilter}
            onCategoryChange={setCategoryFilter}
            categories={categories}
            categoryCounts={categoryCounts}
            status={statusFilter}
            onStatusChange={setStatusFilter}
            statusOptions={STATUS_OPTIONS}
            resultCount={filtered.length}
            totalCount={providers.length}
          />

          <p className="text-[11px] text-muted-foreground">
            CIDR: <strong>БД</strong> — SQLite на контроллере · <strong>Контр.</strong> — собранный
            файл · <strong>Узел</strong> — файл на VPN-сервере
          </p>

          {filtered.length === 0 ? (
            <EmptyState
              icon={Search}
              title="Нет провайдеров по выбранным фильтрам"
              className="py-10"
            />
          ) : (
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {filtered.map((p) => (
                <ProviderListItem
                  key={p.filename}
                  provider={p}
                  cidrDb={cidrDb}
                  readonly={readonly}
                  actionLoading={actionLoading}
                  pipelineBusy={pipelineBusy}
                  onToggle={onToggle}
                  onEdit={(filename, name) => {
                    setEditorFilename(filename)
                    setEditorName(name)
                  }}
                />
              ))}
            </div>
          )}
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
