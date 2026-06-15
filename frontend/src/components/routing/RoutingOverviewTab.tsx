import { GitBranch, Layers, Route, Shield } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getRouteBudget } from '@/api/client'
import MetricCard from '@/components/noc/MetricCard'
import StatusPanel from '@/components/noc/StatusPanel'
import { Badge } from '@/components/ui/badge'
import type { AntifilterStatus, CidrDbStatus, RouteBudgetInfo, RoutingOverview } from '@/types'
import { formatDt, statusBadgeVariant, statusLabel } from './utils'

interface RoutingOverviewTabProps {
  data: RoutingOverview
  cidrDb: CidrDbStatus | null
  antifilter: AntifilterStatus | null
}

export default function RoutingOverviewTab({ data, cidrDb, antifilter }: RoutingOverviewTabProps) {
  const enabledCount = data.providers.filter((p) => p.enabled).length
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
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full bg-primary transition-all"
              style={{
                width: `${Math.min(100, Math.round(((routeBudget.used ?? 0) / Math.max(routeBudget.limit, 1)) * 100))}%`,
              }}
            />
          </div>
          {routeBudget.warning && (
            <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">{routeBudget.warning}</p>
          )}
        </div>
      )}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Провайдеры активны"
          value={enabledCount}
          icon={Route}
          accent="cyan"
          sub={`из ${data.providers.length}`}
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
            Данные и списки сначала на контроллере; на ноды уходит только deploy (этап 3).
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
          </div>
        </StatusPanel>
      </div>
    </div>
  )
}
