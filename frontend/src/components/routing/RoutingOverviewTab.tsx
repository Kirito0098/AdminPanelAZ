import { FileText, GitBranch, Layers, Route } from 'lucide-react'
import MetricCard from '@/components/noc/MetricCard'
import StatusPanel from '@/components/noc/StatusPanel'
import { Badge } from '@/components/ui/badge'
import type { AntifilterStatus, CidrDbStatus, RoutingOverview } from '@/types'
import { formatDt, statusBadgeVariant, statusLabel } from './utils'

interface RoutingOverviewTabProps {
  data: RoutingOverview
  cidrDb: CidrDbStatus | null
  antifilter: AntifilterStatus | null
}

export default function RoutingOverviewTab({ data, cidrDb, antifilter }: RoutingOverviewTabProps) {
  const enabledCount = data.providers.filter((p) => p.enabled).length
  const stats = data.route_stats

  return (
    <div className="space-y-6">
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
          label="Пресеты"
          value={data.presets.length}
          icon={FileText}
          sub="Встроенные"
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
