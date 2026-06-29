import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  AlertTriangle,
  Check,
  CloudDownload,
  Database,
  Loader2,
  Rocket,
  Sparkles,
} from 'lucide-react'
import { Navigate } from 'react-router-dom'
import { ApiError } from '@/api/client'
import { statusLabel } from '@/components/routing/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import MetricCard from '@/components/noc/MetricCard'
import { ROUTING_TAB_UPDATE } from '@/lib/uiLabels'
import { cn } from '@/lib/utils'
import MiniPageHeader from '@/tg-mini/components/MiniPageHeader'
import { getTgCidrStatus } from '@/tg-mini/api'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'
import {
  buildCidrPipelineSteps,
  cidrRefreshMeta,
  formatCidrCount,
  formatCidrDate,
  pipelineTaskStatusLabel,
  type CidrPipelineStep,
} from '@/tg-mini/lib/cidrMini'
import type { TgMiniCidrStatus } from '@/types'

const STAGE_ICONS = {
  1: CloudDownload,
  2: Sparkles,
  3: Rocket,
} as const

function CidrSkeleton() {
  return (
    <div className="tg-mini-dashboard space-y-4" aria-busy="true" aria-label="Загрузка CIDR">
      <div className="tg-mini-skeleton" style={{ height: '2.5rem' }} />
      <div className="tg-mini-cards">
        <div className="tg-mini-skeleton tg-mini-skeleton-card" />
        <div className="tg-mini-skeleton tg-mini-skeleton-card" />
      </div>
      <div className="tg-mini-skeleton tg-mini-skeleton-section" />
      <div className="tg-mini-skeleton tg-mini-skeleton-section" />
    </div>
  )
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="tg-mini-warper-detail">
      <p className="tg-mini-node-meta-label">{label}</p>
      <div className="text-sm font-medium">{children}</div>
    </div>
  )
}

function PipelineStepCard({ step }: { step: CidrPipelineStep }) {
  const Icon = STAGE_ICONS[step.stage]
  return (
    <div
      className={cn(
        'tg-mini-cidr-step',
        step.state === 'done' && 'is-done',
        step.state === 'current' && 'is-current',
        step.state === 'warning' && 'is-warning',
      )}
    >
      <div className="tg-mini-cidr-step-head">
        <div className="tg-mini-cidr-step-icon" aria-hidden>
          {step.state === 'done' ? <Check size={14} /> : <Icon size={14} />}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold">{step.label}</p>
          <p className="truncate text-[11px] text-muted-foreground">{step.summary}</p>
        </div>
        <span className="tg-mini-cidr-step-num">{step.stage}</span>
      </div>
    </div>
  )
}

function ActiveTaskPanel({ data }: { data: TgMiniCidrStatus }) {
  const task = data.pipeline_task
  if (!task?.task_label) return null
  const running = task.status === 'queued' || task.status === 'running'
  if (!running) return null

  const percent = Math.max(0, Math.min(100, task.progress_percent ?? 0))

  return (
    <Card className="tg-mini-cidr-active-task">
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Сейчас выполняется</p>
            <p className="mt-1 text-sm font-semibold">{task.task_label}</p>
            <p className="text-xs text-muted-foreground">{pipelineTaskStatusLabel(task.status)}</p>
          </div>
          <Loader2 size={18} className="shrink-0 animate-spin text-primary" aria-hidden />
        </div>
        <div className="space-y-1.5">
          <div className="tg-mini-cidr-progress" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
            <div className="tg-mini-cidr-progress-bar" style={{ width: `${percent}%` }} />
          </div>
          <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
            <span className="truncate">{task.progress_stage || task.message || 'Обработка…'}</span>
            <span className="shrink-0 tabular-nums">{percent}%</span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default function Cidr() {
  const { isAdmin } = useTgAuth()
  const [data, setData] = useState<TgMiniCidrStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (options?: { silent?: boolean }) => {
    const silent = options?.silent ?? false
    if (silent) {
      setRefreshing(true)
    } else {
      setLoading(true)
    }
    setError(null)
    try {
      setData(await getTgCidrStatus())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    if (!isAdmin) return
    void load()
  }, [isAdmin, load])

  const refreshMeta = useMemo(() => cidrRefreshMeta(data?.last_refresh_status), [data?.last_refresh_status])
  const pipelineSteps = useMemo(() => (data ? buildCidrPipelineSteps(data) : []), [data])

  if (!isAdmin) {
    return <Navigate to="/" replace />
  }

  if (loading) {
    return <CidrSkeleton />
  }

  const compile = data?.last_compile
  const deploy = data?.last_deploy

  return (
    <div className="tg-mini-dashboard space-y-4">
      <MiniPageHeader
        title={`${ROUTING_TAB_UPDATE} CIDR`}
        subtitle="Загрузка → сборка → развёртывание списков маршрутизации"
        onRefresh={() => void load({ silent: true })}
        refreshing={refreshing}
      />

      {error && (
        <div className="tg-mini-inline-alert" role="alert">
          {error}
          <Button type="button" variant="outline" size="sm" className="mt-2" onClick={() => void load()}>
            Повторить
          </Button>
        </div>
      )}

      {data && (
        <>
          <Card className="tg-mini-warper-hero">
            <CardContent className="space-y-3 p-4">
              <div className="flex items-start gap-3">
                <div className="tg-mini-warper-icon" aria-hidden>
                  <Database size={22} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-base font-semibold">База CIDR</h3>
                    <Badge
                      variant={
                        refreshMeta.tone === 'success'
                          ? 'default'
                          : refreshMeta.tone === 'error'
                            ? 'destructive'
                            : 'outline'
                      }
                      className={cn(
                        'font-normal',
                        refreshMeta.tone === 'success' &&
                          'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
                        refreshMeta.tone === 'warning' && 'border-amber-500/40 text-amber-700 dark:text-amber-400',
                      )}
                    >
                      {refreshMeta.label}
                    </Badge>
                    {(data.alerts_count ?? 0) > 0 && (
                      <Badge variant="outline" className="gap-1 font-normal text-amber-700 dark:text-amber-400">
                        <AlertTriangle size={11} aria-hidden />
                        {data.alerts_count} предупр.
                      </Badge>
                    )}
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Обновлено: {formatCidrDate(data.last_refresh_finished)}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="tg-mini-cards">
            <MetricCard
              label="Всего CIDR"
              value={formatCidrCount(data.total_cidrs)}
              sub="в SQLite"
              icon={Database}
              accent={data.total_cidrs > 0 ? 'cyan' : 'default'}
            />
            <MetricCard
              label="Провайдеры"
              value={String(data.providers_loaded ?? 0)}
              sub={`из ${data.providers_total ?? 0} с данными`}
              icon={CloudDownload}
              accent="green"
            />
          </div>

          <ActiveTaskPanel data={data} />

          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Конвейер</p>
            <div className="space-y-2">
              {pipelineSteps.map((step) => (
                <PipelineStepCard key={step.stage} step={step} />
              ))}
            </div>
          </div>

          <Card>
            <CardContent className="space-y-3 p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Последние операции</p>
              <div className="tg-mini-node-meta-grid">
                <DetailRow label="Загрузка">
                  {statusLabel(data.last_refresh_status)}
                </DetailRow>
                <DetailRow label="Завершено">{formatCidrDate(data.last_refresh_finished)}</DetailRow>
                <DetailRow label="Сборка">
                  {compile
                    ? `${statusLabel(String(compile.status ?? ''))} · ${String(compile.files_updated ?? 0)} файлов`
                    : '—'}
                </DetailRow>
                <DetailRow label="Сборка завершена">{formatCidrDate(String(compile?.finished_at ?? ''))}</DetailRow>
                <DetailRow label="Развёртывание">
                  {deploy
                    ? `${statusLabel(String(deploy.status ?? ''))} · ${String(deploy.nodes_deployed ?? 0)} узлов`
                    : '—'}
                </DetailRow>
                <DetailRow label="Деплой завершён">{formatCidrDate(String(deploy?.finished_at ?? ''))}</DetailRow>
              </div>
              {typeof deploy?.failed_count === 'number' && deploy.failed_count > 0 && (
                <p className="rounded-md border border-destructive/30 bg-destructive/5 px-2.5 py-2 text-xs text-destructive">
                  Ошибок при развёртывании: {String(deploy.failed_count)}
                </p>
              )}
            </CardContent>
          </Card>

          <div className="tg-mini-feedback is-info" role="status">
            <Database size={18} className="shrink-0 opacity-70" aria-hidden />
            <p className="text-sm leading-snug">
              Запуск задач и редактирование списков — в веб-панели → Маршрутизация → CIDR.
            </p>
          </div>
        </>
      )}

      {refreshing && (
        <div className="tg-mini-center py-2" aria-live="polite">
          <Loader2 size={18} className="animate-spin text-muted-foreground" aria-hidden />
        </div>
      )}
    </div>
  )
}
