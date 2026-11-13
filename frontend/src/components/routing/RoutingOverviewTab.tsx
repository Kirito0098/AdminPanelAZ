import { GitBranch, Layers, Route, Shield } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getRouteBudget } from '@/api/client'
import MetricCard from '@/components/noc/MetricCard'
import StatusPanel from '@/components/noc/StatusPanel'
import type { RoutingWorkflowState } from '@/components/routing/routingWorkflow'
import { PercentBar } from '@/components/ui/percent-bar'
import { Badge } from '@/components/ui/badge'
import type { AntifilterStatus, RouteBudgetInfo, RoutingOverview } from '@/types'
import { formatDt } from './utils'

interface RoutingOverviewTabProps {
  data: RoutingOverview
  antifilter: AntifilterStatus | null
  workflow: RoutingWorkflowState
  /** Меняется после сборки/развёртывания (например, finished_at из cidrDb) — по нему перезапрашивается бюджет. */
  budgetVersion?: string | number
}

export default function RoutingOverviewTab({
  data,
  antifilter,
  workflow,
  budgetVersion,
}: RoutingOverviewTabProps) {
  const stats = data.route_stats
  const [routeBudget, setRouteBudget] = useState<RouteBudgetInfo | null>(null)

  useEffect(() => {
    void getRouteBudget()
      .then(setRouteBudget)
      .catch(() => setRouteBudget(null))
  }, [budgetVersion])

  const budgetFromArtifacts = routeBudget?.source === 'artifacts'
  const budgetSourceLabel = budgetFromArtifacts
    ? 'По собранным файлам на контроллере'
    : 'По последней оценке обновления CIDR'
  const budgetSourceHint = budgetFromArtifacts
    ? 'Лимит и занятость посчитаны по AP-*-include-ips.txt на контроллере'
    : 'Значения из последней задачи оценки (dry-run) обновления CIDR'
  const budgetSourceTone = budgetFromArtifacts
    ? 'border-emerald-500/40 text-emerald-700 dark:text-emerald-300'
    : 'text-muted-foreground'

  return (
    <div className="space-y-6">
      {routeBudget?.available && routeBudget.limit != null && routeBudget.used != null && (
        <div className="rounded-xl border bg-card p-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-sm font-medium">Бюджет маршрутов OpenVPN</div>
              <div className="text-xs text-muted-foreground">
                {budgetSourceLabel}
                {routeBudget.finished_at ? ` · ${formatDt(routeBudget.finished_at)}` : ''}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className={`text-[10px] ${budgetSourceTone}`} title={budgetSourceHint}>
                {budgetFromArtifacts ? 'артефакты' : 'оценка'}
              </Badge>
              <Badge variant={routeBudget.remaining === 0 ? 'destructive' : 'secondary'}>
                осталось {routeBudget.remaining ?? 0} из {routeBudget.limit}
              </Badge>
            </div>
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
    </div>
  )
}
