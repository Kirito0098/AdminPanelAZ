import { GitBranch, Layers, Route, Shield } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getRouteBudget } from '@/api/client'
import MetricCard from '@/components/noc/MetricCard'
import StatusPanel from '@/components/noc/StatusPanel'
import type { RoutingWorkflowState } from '@/components/routing/routingWorkflow'
import { PercentBar } from '@/components/ui/percent-bar'
import { Badge } from '@/components/ui/badge'
import type { AntifilterStatus, CidrDbStatus, RouteBudgetInfo, RoutingOverview } from '@/types'
import { formatDt, pluralProviders, statusBadgeVariant, statusLabel } from './utils'

interface RoutingOverviewTabProps {
  data: RoutingOverview
  cidrDb: CidrDbStatus | null
  antifilter: AntifilterStatus | null
  workflow: RoutingWorkflowState
}

export default function RoutingOverviewTab({
  data,
  cidrDb,
  antifilter,
  workflow,
}: RoutingOverviewTabProps) {
  const stats = data.route_stats
  const [routeBudget, setRouteBudget] = useState<RouteBudgetInfo | null>(null)

  useEffect(() => {
    void getRouteBudget()
      .then(setRouteBudget)
      .catch(() => setRouteBudget(null))
  }, [])

  return (
    <div className="space-y-6">
      {routeBudget?.available && routeBudget.limit != null && routeBudget.used != null && (
        <div className="rounded-xl border bg-card p-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-sm font-medium">Бюджет маршрутов OpenVPN</div>
              <div className="text-xs text-muted-foreground">
                По последней оценке CIDR pipeline
                {routeBudget.finished_at ? ` · ${formatDt(routeBudget.finished_at)}` : ''}
              </div>
            </div>
            <Badge variant={routeBudget.remaining === 0 ? 'destructive' : 'secondary'}>
              осталось {routeBudget.remaining ?? 0} из {routeBudget.limit}
            </Badge>
          </div>
          <PercentBar
            value={routeBudget.used ?? 0}
            max={Math.max(routeBudget.limit ?? 1, 1)}
            className="h-2"
          />
          {routeBudget.warning && (
            <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">{routeBudget.warning}</p>
          )}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Провайдеры активны"
          value={workflow.enabledCount}
          icon={Route}
          accent="cyan"
          sub={`из ${workflow.onNodeCount} на узле · ${data.providers.length} всего`}
        />
        <MetricCard
          label="Маршруты в config"
          value={stats.config_include_total}
          icon={GitBranch}
          accent="green"
          sub="*include-ips.txt"
        />
        <MetricCard
          label="route-ips.txt"
          value={stats.result_route_ips_count}
          icon={Layers}
          accent={stats.result_route_ips_exists ? 'green' : 'amber'}
          sub={stats.result_route_ips_exists ? 'Сгенерирован' : 'Не сгенерирован'}
        />
        <MetricCard
          label="Antifilter"
          value={antifilter?.cidr_count ?? 0}
          icon={Shield}
          accent="cyan"
          sub="Заблокированные подсети"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <StatusPanel title="Статистика маршрутов" icon={Route}>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Каталог списков</span>
              <span className="mono truncate max-w-[60%] text-right text-xs">{data.list_dir}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Каталог config</span>
              <span className="mono truncate max-w-[60%] text-right text-xs">{data.config_dir}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Обновлено</span>
              <span>{formatDt(data.timestamp)}</span>
            </div>
            {Object.keys(stats.config_include_per_file).length > 0 && (
              <div className="border-t pt-3 space-y-2">
                <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Записей по файлам
                </div>
                {Object.entries(stats.config_include_per_file)
                  .sort(([, a], [, b]) => b - a)
                  .slice(0, 8)
                  .map(([file, count]) => (
                    <div key={file} className="flex justify-between gap-2">
                      <span className="truncate text-xs text-muted-foreground">{file}</span>
                      <span className="mono text-xs font-medium">{count}</span>
                    </div>
                  ))}
              </div>
            )}
          </div>
        </StatusPanel>

        <StatusPanel title="Pipeline CIDR" icon={GitBranch}>
          <p className="mb-3 text-xs text-muted-foreground">
            Данные и списки сначала на контроллере; на узлы уходит только deploy (этап 3).
          </p>
          <div className="space-y-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Статус БД</span>
              <Badge variant={statusBadgeVariant(cidrDb?.last_refresh_status)}>
                {statusLabel(cidrDb?.last_refresh_status)}
              </Badge>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">CIDR в SQLite</span>
              <span className="mono font-medium">{cidrDb?.total_cidrs ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Последний refresh</span>
              <span>{formatDt(cidrDb?.last_refresh_finished)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Antifilter подсетей</span>
              <span className="mono font-medium">{antifilter?.cidr_count ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Antifilter обновлён</span>
              <span>{formatDt(antifilter?.last_refreshed_at)}</span>
            </div>
            {(workflow.pendingCompileCount > 0 || workflow.pendingDeployCount > 0) && (
              <div className="rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-800 dark:text-amber-200 space-y-1">
                {workflow.pendingCompileCount > 0 && !workflow.optionalCompileRemaining && (
                  <div>{pluralProviders(workflow.pendingCompileCount)} ждут сборки (этап 2)</div>
                )}
                {workflow.optionalCompileRemaining && (
                  <div>
                    Сборка завершена ·{' '}
                    {workflow.pendingCompileNames.length === 1
                      ? `«${workflow.pendingCompileNames[0]}» без файла`
                      : `${pluralProviders(workflow.pendingCompileCount)} без файла`}
                    {' '}
                    — необязательно
                  </div>
                )}
                {workflow.pendingDeployCount > 0 && (
                  <div>{pluralProviders(workflow.pendingDeployCount)} ждут deploy (этап 3)</div>
                )}
              </div>
            )}
          </div>
        </StatusPanel>
      </div>
    </div>
  )
}
