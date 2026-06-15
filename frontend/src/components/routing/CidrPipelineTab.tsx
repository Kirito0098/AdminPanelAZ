import { ArrowRight, CloudDownload, History, Info, Play, PlusCircle, Rocket, Shield, Sparkles, Trash2, Undo2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import ProviderFileSelection from '@/components/routing/ProviderFileSelection'
import StatusPanel from '@/components/noc/StatusPanel'
import PipelineStageProgress from '@/components/routing/PipelineStageProgress'
import DeployPreviewPanel from '@/components/routing/DeployPreviewPanel'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import type { AntifilterStatus, CidrDbStatus, CidrDeployPreview, CidrPipelineTask, CidrProviderInfo, Node } from '@/types'
import { formatDt, getPipelineStage, isPipelineRunning, pendingMatchesStage, statusBadgeVariant, statusLabel, type PipelinePendingAction } from './utils'

interface CidrPipelineTabProps {
  providers: CidrProviderInfo[]
  cidrDb: CidrDbStatus | null
  antifilter: AntifilterStatus | null
  pipelineTask: CidrPipelineTask | null
  pendingPipelineAction: PipelinePendingAction | null
  nodes: Node[]
  deployAllOnline: boolean
  deployTargetNodeIds: number[]
  selectedProviderFiles: string[]
  filterAntifilter: boolean
  pipelineBusy: boolean
  onFilterAntifilterChange: (v: boolean) => void
  onDeployAllOnlineChange: (v: boolean) => void
  onDeployTargetNodeIdsChange: (ids: number[]) => void
  onSelectedProviderFilesChange: (files: string[]) => void
  onRefreshDb: () => void
  onRetryFailedProviders: () => void
  onRefreshOne?: (filename: string) => void
  onRefreshAntifilter: () => void
  onGenerate: () => void
  onDeploy: () => void
  onGenerateDoall: () => void
  onClearDb: () => void | Promise<void>
  onOpenCustomWizard: () => void
  onLoadDeployPreview: () => void
  deployPreview: CidrDeployPreview | null
  deployPreviewLoading: boolean
  onRollback: (stamp: string) => void
}

const workflowSteps = [
  { num: 1, text: 'Данные на контроллер (SQLite)' },
  { num: 2, text: 'Списки на контроллере' },
  { num: 3, text: 'Списки на ноду' },
]

function nodeCheckboxLabel(node: Node): string {
  const status =
    node.status === 'online' ? 'online' : node.status === 'offline' ? 'offline' : node.status
  return `${node.name}${node.is_local ? ' (локальная)' : ''} — ${status}`
}

export default function CidrPipelineTab({
  providers,
  cidrDb,
  antifilter,
  pipelineTask,
  pendingPipelineAction,
  nodes,
  deployAllOnline,
  deployTargetNodeIds,
  selectedProviderFiles,
  filterAntifilter,
  pipelineBusy,
  onFilterAntifilterChange,
  onDeployAllOnlineChange,
  onDeployTargetNodeIdsChange,
  onSelectedProviderFilesChange,
  onRefreshDb,
  onRetryFailedProviders,
  onRefreshOne,
  onRefreshAntifilter,
  onGenerate,
  onDeploy,
  onGenerateDoall,
  onClearDb,
  onOpenCustomWizard,
  onLoadDeployPreview,
  deployPreview,
  deployPreviewLoading,
  onRollback,
}: CidrPipelineTabProps) {
  const [confirmClear, setConfirmClear] = useState(false)
  const [clearing, setClearing] = useState(false)
  const onlineNodes = nodes.filter((n) => n.status === 'online')
  const deployDisabled =
    pipelineBusy ||
    selectedProviderFiles.length === 0 ||
    (!deployAllOnline && deployTargetNodeIds.length === 0 && onlineNodes.length === 0)
  const refreshDisabled = pipelineBusy || selectedProviderFiles.length === 0
  const failedProviderCount = providers.filter(
    (p) => cidrDb?.providers?.[p.filename]?.refresh_status === 'error',
  ).length
  const refreshLabel =
    selectedProviderFiles.length > 0 && selectedProviderFiles.length < providers.length
      ? `Обновить выбранные (${selectedProviderFiles.length})`
      : 'Обновить из интернета'

  const activeStage =
    pipelineTask && isPipelineRunning(pipelineTask) ? getPipelineStage(pipelineTask.task_type) : null
  const highlightedStage = activeStage ?? pendingPipelineAction?.stage ?? null

  const toggleNode = (nodeId: number, checked: boolean) => {
    if (checked) {
      onDeployTargetNodeIdsChange([...new Set([...deployTargetNodeIds, nodeId])])
    } else {
      onDeployTargetNodeIdsChange(deployTargetNodeIds.filter((id) => id !== nodeId))
    }
  }

  const needsDeployHint = useMemo(() => {
    const compile = cidrDb?.last_compile_at
    if (!compile?.finished_at || compile.status !== 'completed') return false
    const deploy = cidrDb?.last_deploy
    if (!deploy?.finished_at) return true
    const compileAt = Date.parse(compile.finished_at)
    const deployAt = Date.parse(deploy.finished_at)
    if (!Number.isNaN(compileAt) && !Number.isNaN(deployAt) && compileAt > deployAt) return true
    if (
      compile.artifact_stamp &&
      deploy.artifact_stamp &&
      compile.artifact_stamp !== deploy.artifact_stamp
    ) {
      return true
    }
    return false
  }, [cidrDb?.last_compile_at, cidrDb?.last_deploy])

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/30 p-4 text-sm">
        {workflowSteps.map((step, i) => {
          const isActive = highlightedStage === step.num
          const isPast = highlightedStage != null && step.num < highlightedStage
          return (
            <div key={step.num} className="flex items-center gap-2">
              <span
                className={cn(
                  'flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold transition-colors',
                  isActive
                    ? 'bg-primary text-primary-foreground ring-2 ring-primary ring-offset-2 ring-offset-background animate-pulse'
                    : isPast
                      ? 'bg-emerald-600 text-white'
                      : 'bg-muted-foreground/30 text-muted-foreground',
                )}
              >
                {step.num}
              </span>
              <span className={cn(isActive && 'font-medium text-foreground')}>{step.text}</span>
              {i < workflowSteps.length - 1 && (
                <ArrowRight size={14} className="mx-1 text-muted-foreground" />
              )}
            </div>
          )
        })}
      </div>

      <div className="flex items-start gap-2 rounded-lg border border-primary/30 bg-primary/5 p-4 text-sm">
        <Info size={16} className="mt-0.5 shrink-0 text-primary" />
        <div className="space-y-1 text-muted-foreground">
          <p>
            <strong className="text-foreground">Контроллер → нода:</strong> сначала все данные сохраняются на
            основном сервере (SQLite и файлы списков), затем на этапе 3 готовые списки отправляются на ноды
            AntiZapret. До deploy файлы маршрутизации на нодах не меняются.
          </p>
        </div>
      </div>

      <StatusPanel title="Этап 1 — Данные на контроллере (ingest)" icon={CloudDownload}>
        <p className="mb-4 text-sm text-muted-foreground">
          Загрузка из интернета в SQLite на контроллере. Можно обновить одного или нескольких провайдеров — не
          обязательно все 12 сразу. Ноды не затрагиваются.
        </p>

        <ProviderFileSelection
          providers={providers}
          cidrDb={cidrDb}
          selectedFiles={selectedProviderFiles}
          onSelectedFilesChange={onSelectedProviderFilesChange}
          disabled={pipelineBusy}
          idPrefix="ingest-provider"
          onRefreshOne={onRefreshOne}
          showQuickIngest={Boolean(onRefreshOne)}
        />

        <div className="space-y-4 mb-6 mt-4">
          <div className="rounded-lg border p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-sm font-medium">CIDR провайдеров</div>
                <div className="text-xs text-muted-foreground">RIPE, BGP и др. → таблицы cidr_* в SQLite</div>
              </div>
              <div className="flex flex-wrap gap-2">
                {failedProviderCount > 0 && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={pipelineBusy}
                    onClick={onRetryFailedProviders}
                  >
                    Повторить ошибочные ({failedProviderCount})
                  </Button>
                )}
                <Button size="sm" disabled={refreshDisabled} onClick={onRefreshDb}>
                  <CloudDownload size={14} className="mr-1.5" />
                  {refreshLabel}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={pipelineBusy}
                  onClick={onOpenCustomWizard}
                >
                  <PlusCircle size={14} className="mr-1.5" />
                  Свои ASN/CIDR
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="text-destructive hover:text-destructive"
                  disabled={pipelineBusy}
                  onClick={() => setConfirmClear(true)}
                >
                  <Trash2 size={14} className="mr-1.5" />
                  Очистить БД
                </Button>
              </div>
            </div>
            <PipelineStageProgress
              task={pipelineTask}
              stage={1}
              ingestKind="providers"
              starting={pendingMatchesStage(pendingPipelineAction, 1, 'providers')}
            />
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 text-sm">
              <div className="rounded-md border bg-muted/20 p-3">
                <div className="text-xs text-muted-foreground">Последнее обновление</div>
                <div className="font-medium">{formatDt(cidrDb?.last_refresh_finished)}</div>
                <Badge variant={statusBadgeVariant(cidrDb?.last_refresh_status)} className="mt-1">
                  {statusLabel(cidrDb?.last_refresh_status)}
                </Badge>
              </div>
              <div className="rounded-md border bg-muted/20 p-3">
                <div className="text-xs text-muted-foreground">CIDR в БД</div>
                <div className="mono text-xl font-bold">{cidrDb?.total_cidrs ?? 0}</div>
              </div>
              <div className="rounded-md border bg-muted/20 p-3">
                <div className="text-xs text-muted-foreground">Инициатор</div>
                <div className="text-xs break-all">{cidrDb?.last_refresh_triggered_by ?? '—'}</div>
              </div>
            </div>
          </div>

          <div className="rounded-lg border p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-sm font-medium">Antifilter.download</div>
                <div className="text-xs text-muted-foreground">
                  Заблокированные подсети → SQLite; применяются при сборке списков (этап 2)
                </div>
              </div>
              <Button size="sm" variant="outline" disabled={pipelineBusy} onClick={onRefreshAntifilter}>
                <Shield size={14} className="mr-1.5" />
                Обновить antifilter
              </Button>
            </div>
            <PipelineStageProgress
              task={pipelineTask}
              stage={1}
              ingestKind="antifilter"
              starting={pendingMatchesStage(pendingPipelineAction, 1, 'antifilter')}
            />
            <div className="grid gap-4 sm:grid-cols-2 text-sm">
              <div className="rounded-md border bg-muted/20 p-3">
                <div className="text-xs text-muted-foreground">Подсетей в БД</div>
                <div className="mono text-xl font-bold">{antifilter?.cidr_count ?? 0}</div>
              </div>
              <div className="rounded-md border bg-muted/20 p-3">
                <div className="text-xs text-muted-foreground">Последнее обновление</div>
                <div className="font-medium">{formatDt(antifilter?.last_refreshed_at)}</div>
                <Badge variant={statusBadgeVariant(antifilter?.refresh_status)} className="mt-1">
                  {statusLabel(antifilter?.refresh_status)}
                </Badge>
              </div>
            </div>
          </div>
        </div>
      </StatusPanel>

      <StatusPanel title="Этап 2 — Сборка списков на контроллере (compile)" icon={Sparkles}>
        <PipelineStageProgress
          task={pipelineTask}
          stage={2}
          starting={pendingMatchesStage(pendingPipelineAction, 2)}
        />
        <p className="mb-4 text-sm text-muted-foreground">
          Формирование AP-*-include-ips.txt из локальной БД. Используется выбор провайдеров с этапа 1 (
          {selectedProviderFiles.length} из {providers.length}).
        </p>

        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-4">
          <div className="flex items-center gap-2">
            <input
              id="filter-antifilter"
              type="checkbox"
              checked={filterAntifilter}
              onChange={(e) => onFilterAntifilterChange(e.target.checked)}
              className="h-4 w-4 rounded border"
            />
            <Label htmlFor="filter-antifilter" className="text-sm cursor-pointer">
              Фильтр по antifilter.download
            </Label>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="secondary"
            disabled={pipelineBusy || selectedProviderFiles.length === 0}
            onClick={onGenerate}
          >
            <Sparkles size={14} className="mr-1.5" />
            {selectedProviderFiles.length > 0 && selectedProviderFiles.length < providers.length
              ? `Сгенерировать (${selectedProviderFiles.length})`
              : 'Сгенерировать из БД'}
          </Button>
        </div>

        {(cidrDb?.runtime_backups?.length ?? 0) > 0 && (
          <div className="mt-4 rounded-md border p-4">
            <div className="mb-2 flex items-center gap-2 text-sm font-medium">
              <History size={14} />
              Откат из runtime_backups
            </div>
            <p className="mb-3 text-xs text-muted-foreground">
              Резервные копии создаются перед сборкой списков (этап 2). Откат восстанавливает файлы на контроллере и
              разворачивает их на ноды.
            </p>
            <div className="flex flex-wrap gap-2">
              {cidrDb!.runtime_backups!.slice(0, 5).map((backup) => (
                <Button
                  key={backup.stamp}
                  size="sm"
                  variant="outline"
                  disabled={pipelineBusy}
                  onClick={() => onRollback(backup.stamp)}
                >
                  <Undo2 size={14} className="mr-1.5" />
                  {backup.stamp} ({backup.file_count})
                </Button>
              ))}
            </div>
          </div>
        )}
      </StatusPanel>

      <StatusPanel title="Этап 3 — Списки на ноду (deploy)" icon={Rocket}>
        <PipelineStageProgress
          task={pipelineTask}
          stage={3}
          starting={pendingMatchesStage(pendingPipelineAction, 3)}
        />
        <p className="mb-4 text-sm text-muted-foreground">
          Отправка готовых списков с контроллера на выбранные ноды AntiZapret. Файлы провайдеров:{' '}
          {selectedProviderFiles.length} из {providers.length} (выбор на этапе 1).
        </p>

        {needsDeployHint && (
          <div className="mb-4 flex items-start gap-2 rounded-md border border-sky-500/40 bg-sky-500/10 px-4 py-3 text-sm text-sky-950 dark:text-sky-100">
            <Info size={16} className="mt-0.5 shrink-0" />
            <span>
              Списки уже собраны на контроллере. Следующий шаг — <strong>Deploy</strong> на выбранные
              ноды, затем включение провайдеров на вкладке «CIDR-провайдеры».
            </span>
          </div>
        )}

        <div className="mb-4 space-y-3 rounded-md border p-4">
          <div className="flex items-center gap-2">
            <input
              id="deploy-all-online"
              type="checkbox"
              checked={deployAllOnline}
              onChange={(e) => onDeployAllOnlineChange(e.target.checked)}
              className="h-4 w-4 rounded border"
            />
            <Label htmlFor="deploy-all-online" className="text-sm cursor-pointer font-medium">
              Все online-ноды ({onlineNodes.length})
            </Label>
          </div>

          {!deployAllOnline && (
            <div className="space-y-2 pl-1">
              <div className="text-xs text-muted-foreground">Выберите ноды для развёртывания:</div>
              {nodes.length === 0 ? (
                <div className="text-sm text-muted-foreground">Нет доступных нод</div>
              ) : (
                nodes.map((node) => (
                  <div key={node.id} className="flex items-center gap-2">
                    <input
                      id={`deploy-node-${node.id}`}
                      type="checkbox"
                      checked={deployTargetNodeIds.includes(node.id)}
                      disabled={node.status !== 'online'}
                      onChange={(e) => toggleNode(node.id, e.target.checked)}
                      className="h-4 w-4 rounded border disabled:opacity-50"
                    />
                    <Label
                      htmlFor={`deploy-node-${node.id}`}
                      className={`text-sm cursor-pointer ${node.status !== 'online' ? 'text-muted-foreground' : ''}`}
                    >
                      {nodeCheckboxLabel(node)}
                    </Label>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {cidrDb?.last_deploy && (
          <div className="mb-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4 text-sm">
            <div className="rounded-md border p-3">
              <div className="text-xs text-muted-foreground">Последний deploy</div>
              <div className="font-medium">{formatDt(cidrDb.last_deploy.finished_at)}</div>
              <Badge variant={statusBadgeVariant(cidrDb.last_deploy.status)} className="mt-1">
                {statusLabel(cidrDb.last_deploy.status)}
              </Badge>
            </div>
            <div className="rounded-md border p-3">
              <div className="text-xs text-muted-foreground">Узлов успешно</div>
              <div className="mono text-xl font-bold">{cidrDb.last_deploy.nodes_deployed ?? 0}</div>
            </div>
            <div className="rounded-md border p-3">
              <div className="text-xs text-muted-foreground">Отправлено файлов</div>
              <div className="mono text-xl font-bold">{cidrDb.last_deploy.pushed_count ?? 0}</div>
            </div>
            <div className="rounded-md border p-3">
              <div className="text-xs text-muted-foreground">Пропущено / ошибки</div>
              <div className="mono text-xl font-bold">
                {(cidrDb.last_deploy.nodes_skipped ?? 0) + (cidrDb.last_deploy.nodes_failed ?? 0)}
              </div>
            </div>
          </div>
        )}

        {(cidrDb?.last_deploy?.per_node?.length ?? 0) > 0 && (
          <div className="mb-4 rounded-md border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Нода</TableHead>
                  <TableHead>Статус</TableHead>
                  <TableHead className="text-right">Файлов</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cidrDb!.last_deploy!.per_node!.map((entry) => (
                  <TableRow key={entry.node_id}>
                    <TableCell className="text-sm">
                      {entry.node_name ?? `Узел #${entry.node_id}`}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          entry.status === 'success'
                            ? 'default'
                            : entry.status === 'failed'
                              ? 'destructive'
                              : 'secondary'
                        }
                      >
                        {entry.status === 'success'
                          ? 'Успех'
                          : entry.status === 'failed'
                            ? 'Ошибка'
                            : 'Пропущен'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {entry.pushed_files?.length ?? 0}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        <DeployPreviewPanel preview={deployPreview} loading={deployPreviewLoading} />

        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={deployDisabled}
            onClick={onLoadDeployPreview}
          >
            Dry-run preview
          </Button>
          <Button size="sm" disabled={deployDisabled} onClick={onDeploy}>
            <Rocket size={14} className="mr-1.5" />
            {deployAllOnline ? 'Развернуть на все online' : 'Развернуть на выбранные'}
          </Button>
          <Button size="sm" variant="destructive" disabled={pipelineBusy} onClick={onGenerateDoall}>
            <Play size={14} className="mr-1.5" />
            Сгенерировать + doall
          </Button>
        </div>

        <div className="mt-3 flex items-start gap-2 rounded-md border border-dashed p-3 text-xs text-muted-foreground">
          <Info size={14} className="mt-0.5 shrink-0" />
          <span>
            <strong className="text-foreground">Сгенерировать + doall</strong> — полный цикл: сборка файлов,
            развёртывание на ноду и применение правил (doall.sh). Длительная операция.
          </span>
        </div>
      </StatusPanel>

      {(cidrDb?.history?.length ?? 0) > 0 && (
        <StatusPanel title="История обновлений БД" icon={CloudDownload}>
          <div className="rounded-md border overflow-hidden">
            <div className="max-h-64 overflow-auto">
              <Table>
                <TableHeader className="sticky top-0 bg-muted/95">
                  <TableRow>
                    <TableHead>Начало</TableHead>
                    <TableHead>Окончание</TableHead>
                    <TableHead>Статус</TableHead>
                    <TableHead className="text-right">CIDR</TableHead>
                    <TableHead>Инициатор</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {cidrDb!.history!.map((h) => (
                    <TableRow key={h.id}>
                      <TableCell className="text-xs">{formatDt(h.started_at)}</TableCell>
                      <TableCell className="text-xs">{formatDt(h.finished_at)}</TableCell>
                      <TableCell>
                        <Badge variant={statusBadgeVariant(h.status)}>{statusLabel(h.status)}</Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs">{h.total_cidrs ?? '—'}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{h.triggered_by ?? '—'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        </StatusPanel>
      )}

      <ConfirmDialog
        open={confirmClear}
        onOpenChange={setConfirmClear}
        title="Очистить данные CIDR БД?"
        description={
          selectedProviderFiles.length > 0 && selectedProviderFiles.length < providers.length
            ? `Будут удалены записи SQLite для ${selectedProviderFiles.length} выбранных провайдеров. Файлы на нодах не затрагиваются.`
            : 'Будут удалены все записи провайдеров в SQLite на контроллере. Файлы на нодах не затрагиваются.'
        }
        confirmLabel="Очистить"
        destructive
        loading={clearing}
        onConfirm={async () => {
          setClearing(true)
          try {
            await onClearDb()
            setConfirmClear(false)
          } finally {
            setClearing(false)
          }
        }}
        alert={{
          variant: 'warning',
          title: 'Необратимо на контроллере',
          children: 'После очистки потребуется повторный ingest из интернета.',
        }}
      />
    </div>
  )
}
