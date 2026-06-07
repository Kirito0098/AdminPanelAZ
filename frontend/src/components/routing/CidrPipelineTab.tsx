import { ArrowRight, CloudDownload, Info, Play, Shield, Sparkles } from 'lucide-react'
import StatusPanel from '@/components/noc/StatusPanel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { AntifilterStatus, CidrDbStatus, CidrPipelineTask } from '@/types'
import { formatDt, statusBadgeVariant, statusLabel } from './utils'

interface CidrPipelineTabProps {
  cidrDb: CidrDbStatus | null
  antifilter: AntifilterStatus | null
  pipelineTask: CidrPipelineTask | null
  filterAntifilter: boolean
  pipelineBusy: boolean
  onFilterAntifilterChange: (v: boolean) => void
  onRefreshDb: () => void
  onRefreshAntifilter: () => void
  onGenerate: () => void
  onGenerateDoall: () => void
}

const workflowSteps = [
  { num: 1, text: 'Обновите источники данных' },
  { num: 2, text: 'Настройте фильтры и провайдеров' },
  { num: 3, text: 'Запустите генерацию' },
]

export default function CidrPipelineTab({
  cidrDb,
  antifilter,
  pipelineTask,
  filterAntifilter,
  pipelineBusy,
  onFilterAntifilterChange,
  onRefreshDb,
  onRefreshAntifilter,
  onGenerate,
  onGenerateDoall,
}: CidrPipelineTabProps) {
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

      <StatusPanel title="Источники данных" icon={CloudDownload}>
        <p className="mb-4 text-sm text-muted-foreground">
          Данные загружаются из источников провайдеров в SQLite на контроллере. Генерация файлов
          маршрутизации выполняется по требованию — из БД без обращения к интернету.
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
            Antifilter sync
          </Button>
        </div>

        <div className="mt-3 flex items-start gap-2 rounded-md border border-dashed p-3 text-xs text-muted-foreground">
          <Info size={14} className="mt-0.5 shrink-0" />
          <span>
            <strong className="text-foreground">Antifilter.download</strong> — список заблокированных подсетей.
            При включении фильтра сгенерированные CIDR исключают адреса из этого списка.
          </span>
        </div>
      </StatusPanel>

      <StatusPanel title="Генерация файлов" icon={Sparkles}>
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
          <Button size="sm" variant="destructive" disabled={pipelineBusy} onClick={onGenerateDoall}>
            <Play size={14} className="mr-1.5" />
            Сгенерировать + doall
          </Button>
        </div>
      </StatusPanel>

      {(cidrDb?.history?.length ?? 0) > 0 && (
        <StatusPanel title="История обновлений" icon={CloudDownload}>
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
