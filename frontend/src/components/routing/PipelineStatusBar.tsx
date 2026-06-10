import { AlertTriangle, CloudDownload, Database, FileOutput, Rocket, Shield } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { AntifilterStatus, CidrDbStatus, CidrDegradationAlert } from '@/types'
import { formatDt, statusBadgeVariant, statusLabel } from './utils'

function alertKey(alert: CidrDegradationAlert, index: number): string {
  return `${alert.scope}-${alert.provider_key ?? 'global'}-${alert.level}-${index}`
}

function alertLabel(alert: CidrDegradationAlert): string {
  const provider = alert.provider_key ? `${alert.provider_key}: ` : ''
  return `${provider}${alert.message}`
}

interface PipelineStatusBarProps {
  cidrDb: CidrDbStatus | null
  antifilter: AntifilterStatus | null
}

function deployNodeSummary(lastDeploy: NonNullable<CidrDbStatus['last_deploy']>) {
  const perNode = lastDeploy.per_node ?? []
  if (perNode.length === 0) {
    return null
  }
  return perNode
    .map((entry) => {
      const name = entry.node_name ?? `#${entry.node_id}`
      const label = statusLabel(entry.status)
      return `${name}: ${label}`
    })
    .join(' · ')
}

export default function PipelineStatusBar({ cidrDb, antifilter }: PipelineStatusBarProps) {
  const hasAlerts = (cidrDb?.alerts?.length ?? 0) > 0
  const lastCompile = cidrDb?.last_compile_at
  const lastDeploy = cidrDb?.last_deploy
  const nodeSummary = lastDeploy ? deployNodeSummary(lastDeploy) : null

  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
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
            <div className="text-xs text-muted-foreground">Последний ingest</div>
            <div className="text-sm font-medium">{formatDt(cidrDb?.last_refresh_finished)}</div>
            <div className="text-xs text-muted-foreground truncate">
              {cidrDb?.last_refresh_triggered_by ?? '—'}
            </div>
          </div>
        </div>

        <div className="flex items-start gap-3">
          <div className="rounded-md bg-muted p-2 text-primary">
            <FileOutput size={16} />
          </div>
          <div className="min-w-0">
            <div className="text-xs text-muted-foreground">Последний compile</div>
            {lastCompile ? (
              <>
                <div className="text-sm font-medium">{formatDt(lastCompile.finished_at)}</div>
                <div className="text-xs text-muted-foreground">
                  {lastCompile.files_updated ?? 0} файл(ов)
                  {lastCompile.artifact_stamp && ` · ${lastCompile.artifact_stamp.slice(0, 8)}`}
                </div>
                <Badge variant={statusBadgeVariant(lastCompile.status)} className="mt-1">
                  {statusLabel(lastCompile.status)}
                </Badge>
              </>
            ) : (
              <div className="text-sm text-muted-foreground">Ещё не выполнялся</div>
            )}
          </div>
        </div>

        <div className="flex items-start gap-3">
          <div className="rounded-md bg-muted p-2 text-primary">
            <Rocket size={16} />
          </div>
          <div className="min-w-0">
            <div className="text-xs text-muted-foreground">Последний deploy</div>
            {lastDeploy ? (
              <>
                <div className="text-sm font-medium">{formatDt(lastDeploy.finished_at)}</div>
                <div className="text-xs text-muted-foreground">
                  {(lastDeploy.nodes_deployed ?? 0) > 0 && `${lastDeploy.nodes_deployed} узел(ов), `}
                  {lastDeploy.pushed_count ?? 0} файл(ов)
                  {(lastDeploy.nodes_skipped ?? 0) > 0 && `, пропущено: ${lastDeploy.nodes_skipped}`}
                  {(lastDeploy.failed_count ?? 0) > 0 && `, ошибок: ${lastDeploy.failed_count}`}
                </div>
                {nodeSummary && (
                  <div className="text-xs text-muted-foreground truncate" title={nodeSummary}>
                    {nodeSummary}
                  </div>
                )}
                <Badge variant={statusBadgeVariant(lastDeploy.status)} className="mt-1">
                  {statusLabel(lastDeploy.status)}
                </Badge>
              </>
            ) : (
              <div className="text-sm text-muted-foreground">Ещё не выполнялся</div>
            )}
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
          {cidrDb?.alerts?.map((alert, index) => (
            <div key={alertKey(alert, index)}>{alertLabel(alert)}</div>
          ))}
        </div>
      )}
    </div>
  )
}
