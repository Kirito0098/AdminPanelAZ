import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Cloud,
  CloudOff,
  Copy,
  Globe,
  Loader2,
  Network,
  Server,
} from 'lucide-react'
import { Link, Navigate } from 'react-router-dom'
import { ApiError } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import MetricCard from '@/components/noc/MetricCard'
import { INSTALL_CMD, formatBytes, formatOutboundMode } from '@/components/warper/utils'
import { cn } from '@/lib/utils'
import MiniPageHeader from '@/tg-mini/components/MiniPageHeader'
import { getTgWarperStatus } from '@/tg-mini/api'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'
import { warperNodeLabel, warperStatusMeta } from '@/tg-mini/lib/warperMini'
import type { TgMiniWarperStatus } from '@/types'

function WarperSkeleton() {
  return (
    <div className="tg-mini-dashboard space-y-4" aria-busy="true" aria-label="Загрузка AZ-WARP">
      <div className="tg-mini-skeleton" style={{ height: '2.5rem' }} />
      <div className="tg-mini-skeleton tg-mini-skeleton-summary" />
      <div className="tg-mini-cards">
        <div className="tg-mini-skeleton tg-mini-skeleton-card" />
        <div className="tg-mini-skeleton tg-mini-skeleton-card" />
      </div>
      <div className="tg-mini-skeleton tg-mini-skeleton-section" />
    </div>
  )
}

function CopyInstallCommand() {
  const [hint, setHint] = useState<string | null>(null)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(INSTALL_CMD)
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
      setHint('Скопировано')
      window.setTimeout(() => setHint(null), 1800)
    } catch {
      setHint('Ошибка')
      window.setTimeout(() => setHint(null), 1800)
    }
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-muted-foreground">Установка на узле (root):</p>
      <div className="tg-mini-warper-install-box">
        <pre className="tg-mini-warper-install-cmd">{INSTALL_CMD}</pre>
        <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={() => void copy()}>
          <Copy size={14} aria-hidden />
          {hint ?? 'Скопировать'}
        </Button>
      </div>
    </div>
  )
}

function DetailTile({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="tg-mini-warper-detail">
      <p className="tg-mini-node-meta-label">{label}</p>
      <div className="text-sm font-medium">{children}</div>
    </div>
  )
}

export default function Warper() {
  const { isAdmin } = useTgAuth()
  const [data, setData] = useState<TgMiniWarperStatus | null>(null)
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
      setData(await getTgWarperStatus())
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

  if (!isAdmin) {
    return <Navigate to="/" replace />
  }

  if (loading) {
    return <WarperSkeleton />
  }

  const status = warperStatusMeta(data)
  const installed = Boolean(data?.installed)
  const showMetrics = installed && !data?.conflict_antizapret_warp

  return (
    <div className="tg-mini-dashboard space-y-4">
      <MiniPageHeader
        title="AZ-WARP"
        subtitle="Маршрутизация через Cloudflare WARP на активном узле"
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
                  <Cloud size={22} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-base font-semibold">Состояние</h3>
                    <Badge
                      variant={
                        status.tone === 'success'
                          ? 'default'
                          : status.tone === 'destructive'
                            ? 'destructive'
                            : status.tone === 'warning'
                              ? 'outline'
                              : 'secondary'
                      }
                      className={cn(
                        'gap-1.5 font-normal',
                        status.tone === 'success' && 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
                        status.tone === 'warning' && 'border-amber-500/40 text-amber-700 dark:text-amber-400',
                        data.active && status.tone === 'success' && 'tg-mini-warper-pulse',
                      )}
                    >
                      <span
                        className={cn(
                          'h-2 w-2 rounded-full',
                          status.tone === 'success' && 'bg-emerald-500',
                          status.tone === 'warning' && 'bg-amber-500',
                          status.tone === 'destructive' && 'bg-destructive',
                          status.tone === 'secondary' && 'bg-muted-foreground',
                        )}
                      />
                      {status.label}
                    </Badge>
                    {data.version && (
                      <Badge variant="outline" className="font-mono text-[10px] font-normal">
                        v{data.version}
                      </Badge>
                    )}
                  </div>
                  <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Server size={13} className="shrink-0" aria-hidden />
                    <span className="truncate">{warperNodeLabel(data)}</span>
                  </p>
                  {data.status && data.status !== '—' && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      Ответ API: <span className="font-medium text-foreground">{data.status}</span>
                    </p>
                  )}
                </div>
              </div>

              {data.health_error && (
                <p className="rounded-md border border-destructive/30 bg-destructive/5 px-2.5 py-2 text-xs text-destructive">
                  {data.health_error}
                </p>
              )}
            </CardContent>
          </Card>

          {data.conflict_antizapret_warp && (
            <div className="tg-mini-feedback is-error" role="alert">
              <AlertTriangle size={18} className="shrink-0" aria-hidden />
              <p className="text-sm leading-snug">
                <code className="text-xs">ANTIZAPRET_WARP=y</code> конфликтует с AZ-WARP. Отключите встроенный WARP в
                конфиге AntiZapret в веб-панели.
              </p>
            </div>
          )}

          {showMetrics && (
            <>
              <div className="tg-mini-cards">
                <MetricCard
                  label="Домены"
                  value={data.domain_count == null ? '—' : String(data.domain_count)}
                  sub="в маршрутизации"
                  icon={Globe}
                  accent="cyan"
                />
                <MetricCard
                  label="Исходящий"
                  value={data.traffic_tx == null ? '—' : formatBytes(data.traffic_tx)}
                  sub="сегодня"
                  icon={ArrowUp}
                  accent="green"
                />
              </div>
              <div className="tg-mini-cards">
                <MetricCard
                  label="Входящий"
                  value={data.traffic_rx == null ? '—' : formatBytes(data.traffic_rx)}
                  sub="сегодня"
                  icon={ArrowDown}
                  accent="cyan"
                />
                <Card className="tg-mini-card">
                  <CardContent className="p-3.5">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        Режим
                      </span>
                      <div className="rounded-md bg-muted p-1.5 text-primary">
                        <Activity size={15} aria-hidden />
                      </div>
                    </div>
                    <p className="mt-2 text-base font-bold">
                      {formatOutboundMode(data.outbound_mode)}
                    </p>
                    {data.fake_subnet && (
                      <p className="mt-1 truncate font-mono text-xs text-muted-foreground">{data.fake_subnet}</p>
                    )}
                  </CardContent>
                </Card>
              </div>

              <Card>
                <CardContent className="space-y-3 p-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Детали</p>
                  <div className="tg-mini-node-meta-grid">
                    {data.outbound_mode && (
                      <DetailTile label="Режим выхода">{formatOutboundMode(data.outbound_mode)}</DetailTile>
                    )}
                    {data.fake_subnet && (
                      <DetailTile label="Fake-подсеть">
                        <span className="mono text-xs">{data.fake_subnet}</span>
                      </DetailTile>
                    )}
                    {data.singbox_running != null && (
                      <DetailTile label="sing-box">
                        <Badge variant={data.singbox_running ? 'default' : 'secondary'} className="font-normal">
                          {data.singbox_running ? 'Запущен' : 'Остановлен'}
                        </Badge>
                      </DetailTile>
                    )}
                    {data.kresd_patched != null && (
                      <DetailTile label="kresd">
                        <Badge variant={data.kresd_patched ? 'default' : 'secondary'} className="font-normal">
                          {data.kresd_patched ? 'Пропатчен' : 'Не пропатчен'}
                        </Badge>
                      </DetailTile>
                    )}
                  </div>
                  {data.fake_subnet && (
                    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed bg-muted/20 px-3 py-2.5 text-xs text-muted-foreground">
                      <Network size={14} aria-hidden />
                      <span>Трафик доменов уходит через fake-подсеть</span>
                      <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-foreground">
                        {data.fake_subnet}
                      </code>
                    </div>
                  )}
                </CardContent>
              </Card>
            </>
          )}

          {!installed && !data.conflict_antizapret_warp && (
            <div className="tg-mini-filter-empty">
              <CloudOff size={24} className="text-muted-foreground" aria-hidden />
              <p className="text-sm font-medium">AZ-WARP не установлен</p>
              <p className="max-w-sm text-xs text-muted-foreground">
                На узле <strong>{data.node_name}</strong> нет AZ-WARP. Установите на сервере или переключите активный
                узел.
              </p>
              <CopyInstallCommand />
              <Button type="button" variant="outline" size="sm" asChild>
                <Link to="/nodes">Перейти к узлам</Link>
              </Button>
            </div>
          )}

          {installed && !data.active && !data.conflict_antizapret_warp && (
            <div className="tg-mini-feedback is-info" role="status">
              <Activity size={18} className="shrink-0 opacity-70" aria-hidden />
              <p className="text-sm leading-snug">
                WARP установлен, но выключен. Включите и настройте в веб-панели → AZ-WARP.
              </p>
            </div>
          )}
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
