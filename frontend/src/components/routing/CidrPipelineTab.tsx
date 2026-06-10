import { ArrowRight, CloudDownload, Info, Play, Rocket, Shield, Sparkles } from 'lucide-react'
import StatusPanel from '@/components/noc/StatusPanel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { AntifilterStatus, CidrDbStatus, CidrPipelineTask, Node } from '@/types'
import { formatDt, statusBadgeVariant, statusLabel } from './utils'

interface CidrPipelineTabProps {
  cidrDb: CidrDbStatus | null
  antifilter: AntifilterStatus | null
  pipelineTask: CidrPipelineTask | null
  nodes: Node[]
  deployAllOnline: boolean
  deployTargetNodeIds: number[]
  filterAntifilter: boolean
  pipelineBusy: boolean
  onFilterAntifilterChange: (v: boolean) => void
  onDeployAllOnlineChange: (v: boolean) => void
  onDeployTargetNodeIdsChange: (ids: number[]) => void
  onRefreshDb: () => void
  onRefreshAntifilter: () => void
  onGenerate: () => void
  onDeploy: () => void
  onGenerateDoall: () => void
}

const workflowSteps = [
  { num: 1, text: 'Обновить БД из интернета' },
  { num: 2, text: 'Собрать CIDR-файлы на контроллере' },
  { num: 3, text: 'Развернуть файлы на ноду' },
]

function nodeCheckboxLabel(node: Node): string {
  const status =
    node.status === 'online' ? 'online' : node.status === 'offline' ? 'offline' : node.status
  return `${node.name}${node.is_local ? ' (локальная)' : ''} — ${status}`
}

export default function CidrPipelineTab({
  cidrDb,
  antifilter,
  pipelineTask: _pipelineTask,
  nodes,
  deployAllOnline,
  deployTargetNodeIds,
  filterAntifilter,
  pipelineBusy,
  onFilterAntifilterChange,
  onDeployAllOnlineChange,
  onDeployTargetNodeIdsChange,
  onRefreshDb,
  onRefreshAntifilter,
  onGenerate,
  onDeploy,
  onGenerateDoall,
}: CidrPipelineTabProps) {
  const onlineNodes = nodes.filter((n) => n.status === 'online')
  const deployDisabled =
    pipelineBusy || (!deployAllOnline && deployTargetNodeIds.length === 0 && onlineNodes.length === 0)

  const toggleNode = (nodeId: number, checked: boolean) => {
    if (checked) {
      onDeployTargetNodeIdsChange([...new Set([...deployTargetNodeIds, nodeId])])
    } else {
      onDeployTargetNodeIdsChange(deployTargetNodeIds.filter((id) => id !== nodeId))
    }
  }
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/30 p-4 text-sm">
        {workflowSteps.map((step, i) => (
          <div key={step.num} className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
              {step.num}
            </span>
            <span>{step.text}</span>
            {i < workflowSteps.length - 1 && (
              <ArrowRight size={14} className="mx-1 text-muted-foreground" />
            )}
          </div>
        ))}
      </div>

      <StatusPanel title="Этап 1 — Обновление БД (ingest)" icon={CloudDownload}>
        <p className="mb-4 text-sm text-muted-foreground">
          Загрузка CIDR провайдеров из интернета в SQLite на контроллере. Не затрагивает файлы
          маршрутизации на нодах — только локальную базу данных.
        </p>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 text-sm mb-6">
          <div className="rounded-md border p-3">
            <div className="text-xs text-muted-foreground">Последнее обновление БД</div>
            <div className="font-medium">{formatDt(cidrDb?.last_refresh_finished)}</div>
            <Badge variant={statusBadgeVariant(cidrDb?.last_refresh_status)} className="mt-1">
              {statusLabel(cidrDb?.last_refresh_status)}
            </Badge>
          </div>
          <div className="rounded-md border p-3">
            <div className="text-xs text-muted-foreground">CIDR в БД</div>
            <div className="mono text-xl font-bold">{cidrDb?.total_cidrs ?? 0}</div>
          </div>
          <div className="rounded-md border p-3">
            <div className="text-xs text-muted-foreground">Antifilter</div>
            <div className="mono text-xl font-bold">{antifilter?.cidr_count ?? 0}</div>
            <div className="text-xs text-muted-foreground mt-1">{formatDt(antifilter?.last_refreshed_at)}</div>
          </div>
          <div className="rounded-md border p-3">
            <div className="text-xs text-muted-foreground">Инициатор</div>
            <div className="text-xs break-all">{cidrDb?.last_refresh_triggered_by ?? '—'}</div>
          </div>
        </div>

        <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-end">
          <Button size="sm" disabled={pipelineBusy} onClick={onRefreshDb}>
            <CloudDownload size={14} className="mr-1.5" />
            Обновить из интернета
          </Button>
          <Button size="sm" variant="outline" disabled={pipelineBusy} onClick={onRefreshAntifilter}>
            <Shield size={14} className="mr-1.5" />
            Обновить antifilter
          </Button>
        </div>

        <div className="mt-3 flex items-start gap-2 rounded-md border border-dashed p-3 text-xs text-muted-foreground">
          <Info size={14} className="mt-0.5 shrink-0" />
          <span>
            <strong className="text-foreground">Antifilter.download</strong> — список заблокированных подсетей.
            При включении фильтра на этапе 2 сгенерированные CIDR исключают адреса из этого списка.
          </span>
        </div>
      </StatusPanel>

      <StatusPanel title="Этап 2 — Сборка файлов (compile)" icon={Sparkles}>
        <p className="mb-4 text-sm text-muted-foreground">
          Генерация AP-*-include-ips.txt из локальной БД на контроллере. Файлы сохраняются в{' '}
          <code className="text-xs">backend/data/cidr/list</code> и не отправляются на ноду автоматически.
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
          <Button size="sm" variant="secondary" disabled={pipelineBusy} onClick={onGenerate}>
            <Sparkles size={14} className="mr-1.5" />
            Сгенерировать из БД
          </Button>
        </div>
      </StatusPanel>

      <StatusPanel title="Этап 3 — Развёртывание на ноду (deploy)" icon={Rocket}>
        <p className="mb-4 text-sm text-muted-foreground">
          Отправка ранее собранных CIDR-файлов с контроллера на выбранные ноды AntiZapret и синхронизация
          провайдеров. Offline-ноды пропускаются. Можно запускать отдельно, без повторной генерации.
        </p>

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

        <div className="flex flex-wrap gap-2">
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
    </div>
  )
}
