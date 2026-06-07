import { AlertTriangle, CloudDownload, Database, Shield } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { AntifilterStatus, CidrDbStatus } from '@/types'
import { formatDt, statusBadgeVariant, statusLabel } from './utils'

interface PipelineStatusBarProps {
  cidrDb: CidrDbStatus | null
  antifilter: AntifilterStatus | null
}

export default function PipelineStatusBar({ cidrDb, antifilter }: PipelineStatusBarProps) {
  const hasAlerts = (cidrDb?.alerts?.length ?? 0) > 0

  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="flex items-start gap-3">
          <div className="rounded-md bg-muted p-2 text-primary">
            <Database size={16} />
          </div>
          <div className="min-w-0">
            <div className="text-xs text-muted-foreground">CIDR в БД</div>
            <div className="mono text-lg font-bold">{cidrDb?.total_cidrs ?? 0}</div>
            <Badge variant={statusBadgeVariant(cidrDb?.last_refresh_status)} className="mt-1">
              {statusLabel(cidrDb?.last_refresh_status)}
            </Badge>
          </div>
        </div>

        <div className="flex items-start gap-3">
          <div className="rounded-md bg-muted p-2 text-primary">
            <CloudDownload size={16} />
          </div>
          <div className="min-w-0">
            <div className="text-xs text-muted-foreground">Последнее обновление БД</div>
            <div className="text-sm font-medium">{formatDt(cidrDb?.last_refresh_finished)}</div>
            <div className="text-xs text-muted-foreground truncate">
              {cidrDb?.last_refresh_triggered_by ?? '—'}
            </div>
          </div>
        </div>

        <div className="flex items-start gap-3">
          <div className="rounded-md bg-muted p-2 text-primary">
            <Shield size={16} />
          </div>
          <div className="min-w-0">
            <div className="text-xs text-muted-foreground">Antifilter.download</div>
            <div className="mono text-lg font-bold">{antifilter?.cidr_count ?? 0}</div>
            <div className="text-xs text-muted-foreground">{formatDt(antifilter?.last_refreshed_at)}</div>
          </div>
        </div>

        <div className="flex items-start gap-3">
          <div className={`rounded-md p-2 ${hasAlerts ? 'bg-amber-500/10 text-amber-600' : 'bg-muted text-muted-foreground'}`}>
            <AlertTriangle size={16} />
          </div>
          <div className="min-w-0">
            <div className="text-xs text-muted-foreground">Предупреждения</div>
            {hasAlerts ? (
              <div className="text-sm text-amber-700 dark:text-amber-300">
                {cidrDb!.alerts!.length} активных
              </div>
            ) : (
              <div className="text-sm font-medium text-emerald-600 dark:text-emerald-400">Нет ошибок</div>
            )}
          </div>
        </div>
      </div>

      {hasAlerts && (
        <div className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-200 space-y-1">
          {cidrDb?.alerts?.map((a) => (
            <div key={a}>{a}</div>
          ))}
        </div>
      )}
    </div>
  )
}
