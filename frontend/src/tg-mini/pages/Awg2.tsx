import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  Activity,
  Copy,
  Loader2,
  Network,
  Server,
  Shield,
  ShieldOff,
  Users,
} from 'lucide-react'
import { Link, Navigate } from 'react-router-dom'
import { ApiError } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import MetricCard from '@/components/noc/MetricCard'
import { formatBytes } from '@/components/warper/utils'
import { cn } from '@/lib/utils'
import MiniPageHeader from '@/tg-mini/components/MiniPageHeader'
import { getTgAwg2Status } from '@/tg-mini/api'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'
import { awg2NodeLabel, awg2StatusMeta } from '@/tg-mini/lib/awg2Mini'
import type { TgMiniAwg2Status } from '@/types'

function Awg2Skeleton() {
  return (
    <div className="tg-mini-dashboard space-y-4" aria-busy="true" aria-label="Загрузка AZ-AWG2">
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

function CopyInstallCommand({ command }: { command: string }) {
  const [hint, setHint] = useState<string | null>(null)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command)
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
      <p className="text-xs font-medium text-muted-foreground">Установка на узле (SSH):</p>
      <div className="tg-mini-warper-install-box">
        <pre className="tg-mini-warper-install-cmd">{command}</pre>
        <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={() => void copy()}>
          <Copy size={14} aria-hidden />
          {hint ?? 'Скопировать'}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Install/обфускация из Mini App недоступны — используйте веб-панель → AZ-AWG2.
      </p>
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

export default function Awg2() {
  const { isAdmin } = useTgAuth()
  const [data, setData] = useState<TgMiniAwg2Status | null>(null)
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
      setData(await getTgAwg2Status())
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
    return <Awg2Skeleton />
  }

  const status = awg2StatusMeta(data)
  const installed = Boolean(data?.installed)

  return (
    <div className="tg-mini-dashboard space-y-4">
      <MiniPageHeader
        title="AZ-AWG2"
        subtitle="AmneziaWG 2.0 на активном узле (только просмотр)"
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
                  <Shield size={22} />
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
                        status.tone === 'success' &&
                          'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
                        status.tone === 'warning' && 'border-amber-500/40 text-amber-700 dark:text-amber-400',
                        installed && status.tone === 'success' && 'tg-mini-warper-pulse',
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
                  </div>
                  <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Server size={13} className="shrink-0" aria-hidden />
                    <span className="truncate">{awg2NodeLabel(data)}</span>
                  </p>
                </div>
              </div>

              {data.health_error && (
                <p className="rounded-md border border-destructive/30 bg-destructive/5 px-2.5 py-2 text-xs text-destructive">
                  {data.health_error}
                </p>
              )}
            </CardContent>
          </Card>

          {installed && (
            <>
              <div className="tg-mini-cards">
                <MetricCard
                  label="Online"
                  value={String(data.online_count)}
                  sub="пиры сейчас"
                  icon={Activity}
                  accent="green"
                />
                <MetricCard
                  label="Peers"
                  value={String(data.peer_count)}
                  sub="в мониторинге"
                  icon={Users}
                  accent="cyan"
                />
              </div>

              <Card>
                <CardContent className="space-y-3 p-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Детали</p>
                  <div className="tg-mini-node-meta-grid">
                    <DetailTile label="Интерфейсы">
                      <span className="font-mono text-xs">{data.ifaces_summary || '—'}</span>
                    </DetailTile>
                  </div>
                  {data.top_traffic.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-xs font-medium text-muted-foreground">Топ трафика</p>
                      <ul className="space-y-1.5 text-sm">
                        {data.top_traffic.map((row) => (
                          <li key={row.name} className="flex items-center justify-between gap-2">
                            <span className="truncate font-medium">{row.name}</span>
                            <span className="shrink-0 text-xs text-muted-foreground">
                              ↓{formatBytes(row.rx)} · ↑{formatBytes(row.tx)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </CardContent>
              </Card>
            </>
          )}

          {!installed && (
            <div className="tg-mini-filter-empty">
              <ShieldOff size={24} className="text-muted-foreground" aria-hidden />
              <p className="text-sm font-medium">AZ-AWG2 не установлен</p>
              <p className="max-w-sm text-xs text-muted-foreground">
                На узле <strong>{data.node_name}</strong> нет слоя AmneziaWG 2.0.
                {data.missing_components.length > 0 && (
                  <> Не хватает: {data.missing_components.join(', ')}.</>
                )}
              </p>
              {data.install_command && <CopyInstallCommand command={data.install_command} />}
              <Button type="button" variant="outline" size="sm" asChild>
                <Link to="/nodes">Перейти к узлам</Link>
              </Button>
            </div>
          )}

          {installed && (
            <div className="tg-mini-feedback is-info" role="status">
              <Network size={18} className="shrink-0 opacity-70" aria-hidden />
              <p className="text-sm leading-snug">
                Установка, обфускация и бэкап — только в веб-панели → AZ-AWG2. Конфиги создавайте во вкладке
                «Конфиги».
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
