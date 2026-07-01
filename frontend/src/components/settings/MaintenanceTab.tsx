import { useCallback, useEffect, useState, type ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  AlertTriangle,
  Copy,
  Database,
  FolderOpen,
  Globe,
  HardDrive,
  MapPin,
  Play,
  RefreshCw,
  RotateCcw,
  Save,
  ServerCrash,
  Sparkles,
  Timer,
} from 'lucide-react'
import {
  ApiError,
  getGeoIpStatus,
  getRetentionSettings,
  recreateProfiles,
  restartService,
  runDoall,
  updateRetentionSettings,
} from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { getVpnServiceLabel } from '@/components/settings/settingsLabels'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Switch } from '@/components/ui/switch'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { cn } from '@/lib/utils'
import type { AppSettings, GeoIpStatus, RetentionSettings } from '@/types'

const SERVICES = [
  'openvpn-server@antizapret-udp',
  'openvpn-server@antizapret-tcp',
  'openvpn-server@vpn-udp',
  'openvpn-server@vpn-tcp',
  'wg-quick@antizapret',
  'wg-quick@vpn',
] as const

const RETENTION_PRESETS = [
  { id: 'compact', label: 'Экономия', traffic: 14, logs: 14, metrics: 7 },
  { id: 'balanced', label: 'Стандарт', traffic: 30, logs: 30, metrics: 14 },
  { id: 'long', label: 'Долго', traffic: 90, logs: 90, metrics: 30 },
] as const

const INTERVAL_PRESETS = [6, 12, 24] as const

interface MaintenanceTabProps {
  settings: AppSettings | null
}

function SectionHeading({
  title,
  description,
}: {
  title: string
  description: string
}) {
  return (
    <div className="md:col-span-2">
      <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
      <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
    </div>
  )
}

function ToggleRow({
  id,
  label,
  description,
  checked,
  disabled,
  onCheckedChange,
}: {
  id: string
  label: string
  description?: string
  checked: boolean
  disabled?: boolean
  onCheckedChange: (checked: boolean) => void
}) {
  return (
    <div
      className={cn(
        'flex items-start justify-between gap-4 rounded-xl border bg-card/50 p-4 transition-colors',
        disabled && 'opacity-60',
      )}
    >
      <div className="min-w-0 space-y-1">
        <Label htmlFor={id} className={cn('font-medium', !disabled && 'cursor-pointer')}>
          {label}
        </Label>
        {description && <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>}
      </div>
      <Switch id={id} checked={checked} disabled={disabled} onCheckedChange={onCheckedChange} />
    </div>
  )
}

function MetricPill({
  icon: Icon,
  label,
  value,
  tone = 'default',
}: {
  icon: LucideIcon
  label: string
  value: string
  tone?: 'default' | 'success' | 'muted'
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-card/80 p-3 shadow-sm backdrop-blur-sm">
      <div
        className={cn(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl',
          tone === 'success' && 'bg-primary/15 text-primary',
          tone === 'muted' && 'bg-muted text-muted-foreground',
          tone === 'default' && 'bg-muted/80 text-foreground',
        )}
      >
        <Icon size={18} />
      </div>
      <div className="min-w-0">
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="truncate text-sm font-semibold">{value}</p>
      </div>
    </div>
  )
}

function ActionCard({
  icon: Icon,
  title,
  description,
  impact,
  impactLabel,
  points,
  stripeClass,
  iconClass,
  children,
}: {
  icon: LucideIcon
  title: string
  description: string
  impact: 'low' | 'medium' | 'high'
  impactLabel: string
  points: string[]
  stripeClass: string
  iconClass: string
  children: ReactNode
}) {
  const impactVariant =
    impact === 'high' ? 'destructive' : impact === 'medium' ? 'secondary' : 'outline'

  return (
    <Card className="relative h-full overflow-hidden border-border/80 shadow-sm">
      <div className={cn('absolute inset-x-0 top-0 h-1', stripeClass)} />
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className={cn('flex h-11 w-11 shrink-0 items-center justify-center rounded-xl', iconClass)}>
              <Icon size={20} />
            </div>
            <div>
              <CardTitle className="text-base">{title}</CardTitle>
              <CardDescription className="mt-1">{description}</CardDescription>
            </div>
          </div>
          <Badge variant={impactVariant} className="shrink-0 text-[10px]">
            {impactLabel}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <ul className="space-y-1.5 text-xs text-muted-foreground">
          {points.map((point) => (
            <li key={point} className="flex gap-2">
              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-primary/70" />
              <span>{point}</span>
            </li>
          ))}
        </ul>
        {children}
      </CardContent>
    </Card>
  )
}

export default function MaintenanceTab({ settings }: MaintenanceTabProps) {
  const { success, error: notifyError } = useNotifications()
  const { withInline, trackBackgroundTask } = useProgress()
  const [service, setService] = useState<string>(SERVICES[0])
  const [busy, setBusy] = useState<string | null>(null)
  const [retention, setRetention] = useState<RetentionSettings | null>(null)
  const [retentionSaving, setRetentionSaving] = useState(false)
  const [geoIpStatus, setGeoIpStatus] = useState<GeoIpStatus | null>(null)
  const [geoIpLoading, setGeoIpLoading] = useState(false)

  const loadGeoIpStatus = useCallback(async () => {
    setGeoIpLoading(true)
    try {
      setGeoIpStatus(await getGeoIpStatus())
    } catch {
      setGeoIpStatus(null)
    } finally {
      setGeoIpLoading(false)
    }
  }, [])

  useEffect(() => {
    void getRetentionSettings()
      .then(setRetention)
      .catch(() => setRetention(null))
    void loadGeoIpStatus()
  }, [loadGeoIpStatus])

  const saveRetention = async (snapshot: RetentionSettings) => {
    setRetentionSaving(true)
    try {
      const updated = await updateRetentionSettings(snapshot)
      setRetention(updated)
      success('Настройки очистки сохранены')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось сохранить настройки очистки')
    } finally {
      setRetentionSaving(false)
    }
  }

  const saveRetentionPatch = (patch: Partial<RetentionSettings>) => {
    if (!retention) return
    const next = { ...retention, ...patch }
    setRetention(next)
    void saveRetention(next)
  }

  const applyRetentionPreset = (preset: (typeof RETENTION_PRESETS)[number]) => {
    if (!retention) return
    setRetention({
      ...retention,
      traffic_sample_retention_days: preset.traffic,
      action_log_retention_days: preset.logs,
      resource_metrics_retention_days: preset.metrics,
    })
  }

  const run = async (key: string, label: string, fn: () => Promise<unknown>) => {
    setBusy(key)
    try {
      await withInline(fn, label)
      success('Операция выполнена')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка операции')
    } finally {
      setBusy(null)
    }
  }

  const copyPath = async (path: string) => {
    try {
      await navigator.clipboard.writeText(path)
      success('Путь скопирован')
    } catch {
      notifyError('Не удалось скопировать')
    }
  }

  const geoLoaded = geoIpStatus?.loaded ?? false
  const activePresetId = retention
    ? RETENTION_PRESETS.find(
        (p) =>
          p.traffic === retention.traffic_sample_retention_days &&
          p.logs === retention.action_log_retention_days &&
          p.metrics === retention.resource_metrics_retention_days,
      )?.id
    : undefined

  return (
    <div className="space-y-4">
      <InlineProgressBar active={retentionSaving} label="Сохранение настроек очистки..." />

      <div className="grid gap-4 md:grid-cols-2 md:items-start">
        <div className="relative overflow-hidden rounded-xl border bg-gradient-to-br from-primary/5 via-card to-card p-4 md:col-span-2">
          <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-primary/10 blur-2xl" />
          <div className="relative grid gap-3 sm:grid-cols-2">
            <MetricPill
              icon={Globe}
              label="Геолокация"
              value={geoIpStatus ? (geoLoaded ? 'Локальная база' : 'Онлайн-сервис') : '…'}
              tone={geoLoaded ? 'success' : 'muted'}
            />
            <MetricPill
              icon={Database}
              label="Автоочистка"
              value={retention?.enabled ? 'Активна' : 'Выключена'}
              tone={retention?.enabled ? 'success' : 'muted'}
            />
          </div>
        </div>

        <SectionHeading
          title="Операции с VPN"
          description="Запускайте в период низкой нагрузки — клиенты могут кратковременно отключиться"
        />

        <ActionCard
          icon={Sparkles}
          title="Полное обновление"
          description="doall.sh — маршруты, списки и профили за один раз"
          impact="medium"
          impactLabel="Прерывание VPN"
          stripeClass="bg-gradient-to-r from-primary/70 to-primary/20"
          iconClass="bg-primary/15 text-primary"
          points={[
            'Применяет маршрутизацию на сервере',
            'Обновляет списки и конфигурации',
            'Прогресс отображается вверху страницы',
          ]}
        >
          <Button
            className="w-full"
            size="lg"
            disabled={!!busy}
            onClick={async () => {
              setBusy('doall')
              try {
                const resp = await runDoall()
                trackBackgroundTask(resp.task_id, {
                  onComplete: () => success(resp.message || 'Обновление VPN завершено'),
                  onError: (task, message) => notifyError(task?.error || task?.message || message),
                })
              } catch (err) {
                notifyError(err instanceof ApiError ? err.message : 'Не удалось запустить обновление')
              } finally {
                setBusy(null)
              }
            }}
          >
            <Play size={18} className={busy === 'doall' ? 'animate-spin' : ''} />
            {busy === 'doall' ? 'Запуск...' : 'Запустить обновление'}
          </Button>
        </ActionCard>

        <ActionCard
          icon={RotateCcw}
          title="Профили клиентов"
          description="Пересоздать .ovpn / WireGuard без полного doall"
          impact="medium"
          impactLabel="Переподключение"
          stripeClass="bg-gradient-to-r from-amber-500/70 to-amber-500/15"
          iconClass="bg-amber-500/15 text-amber-600 dark:text-amber-400"
          points={[
            'Обновляет файлы подключения клиентов',
            'Быстрее, чем полное обновление',
            'Не затрагивает маршрутизацию',
          ]}
        >
          <Button
            className="w-full"
            size="lg"
            variant="outline"
            disabled={!!busy}
            onClick={() => run('recreate', 'Пересоздание профилей...', recreateProfiles)}
          >
            <RotateCcw size={18} className={busy === 'recreate' ? 'animate-spin' : ''} />
            {busy === 'recreate' ? 'Выполняется...' : 'Пересоздать профили'}
          </Button>
        </ActionCard>

        <SectionHeading
          title="Хранение и карта"
          description="Автоочистка журналов и база стран для дашборда"
        />

        {retention && (
          <Card className="shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <HardDrive size={18} />
                Очистка данных
              </CardTitle>
              <CardDescription>Старые записи трафика, журнала и метрик сервера</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <ToggleRow
                id="retention-enabled"
                label="Автоочистка по расписанию"
                description="Удаление устаревших данных без ручного вмешательства"
                checked={retention.enabled}
                onCheckedChange={(checked) => saveRetentionPatch({ enabled: checked })}
              />

              {retention.enabled && (
                <>
                  <div className="space-y-3 rounded-xl border bg-muted/20 p-4">
                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">Профиль хранения</Label>
                      <div className="flex flex-wrap gap-2">
                        {RETENTION_PRESETS.map((preset) => (
                          <button
                            key={preset.id}
                            type="button"
                            onClick={() => applyRetentionPreset(preset)}
                            className={cn(
                              'rounded-lg border px-3 py-1.5 text-sm font-medium transition-all',
                              activePresetId === preset.id
                                ? 'border-primary bg-primary/10 text-primary ring-1 ring-primary'
                                : 'hover:border-muted-foreground/30 hover:bg-muted/50',
                            )}
                          >
                            {preset.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <Timer size={12} />
                        Интервал проверки
                      </Label>
                      <div className="flex flex-wrap items-center gap-2">
                        {INTERVAL_PRESETS.map((h) => (
                          <button
                            key={h}
                            type="button"
                            onClick={() => setRetention({ ...retention, interval_hours: h })}
                            className={cn(
                              'rounded-lg border px-3 py-1.5 text-sm transition-colors',
                              retention.interval_hours === h
                                ? 'border-primary bg-primary/10 text-primary'
                                : 'hover:bg-muted/50',
                            )}
                          >
                            {h} ч
                          </button>
                        ))}
                        <Input
                          type="number"
                          min={1}
                          max={168}
                          className="h-9 w-20"
                          value={retention.interval_hours}
                          onChange={(e) =>
                            setRetention({ ...retention, interval_hours: Number(e.target.value) })
                          }
                        />
                      </div>
                    </div>

                    <div className="grid gap-3 sm:grid-cols-3">
                      <div className="space-y-1.5">
                        <Label htmlFor="retention-traffic" className="text-xs">
                          Трафик, дн.
                        </Label>
                        <Input
                          id="retention-traffic"
                          type="number"
                          min={1}
                          value={retention.traffic_sample_retention_days}
                          onChange={(e) =>
                            setRetention({
                              ...retention,
                              traffic_sample_retention_days: Number(e.target.value),
                            })
                          }
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="retention-logs" className="text-xs">
                          Журнал, дн.
                        </Label>
                        <Input
                          id="retention-logs"
                          type="number"
                          min={1}
                          value={retention.action_log_retention_days}
                          onChange={(e) =>
                            setRetention({ ...retention, action_log_retention_days: Number(e.target.value) })
                          }
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="retention-node-metrics" className="text-xs">
                          Метрики, дн.
                        </Label>
                        <Input
                          id="retention-node-metrics"
                          type="number"
                          min={1}
                          value={retention.resource_metrics_retention_days}
                          onChange={(e) =>
                            setRetention({
                              ...retention,
                              resource_metrics_retention_days: Number(e.target.value),
                            })
                          }
                        />
                      </div>
                    </div>
                  </div>

                  <div className="flex justify-end">
                    <Button type="button" disabled={retentionSaving} onClick={() => void saveRetention(retention)}>
                      <Save size={16} />
                      {retentionSaving ? 'Сохранение...' : 'Сохранить сроки'}
                    </Button>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        )}

        <div className="flex flex-col gap-3 self-start">
          <Card className="shadow-sm">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 pt-4">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                <MapPin size={16} />
                Страна по IP
              </CardTitle>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0"
                disabled={geoIpLoading}
                onClick={() => void loadGeoIpStatus()}
              >
                <RefreshCw size={14} className={geoIpLoading ? 'animate-spin' : ''} />
              </Button>
            </CardHeader>
            <CardContent className="space-y-3 pb-4">
              <div className="flex items-center gap-2">
                <Badge variant={geoLoaded ? 'default' : 'secondary'}>
                  {geoIpStatus
                    ? geoLoaded
                      ? 'Локальная база'
                      : 'Онлайн-сервис'
                    : '…'}
                </Badge>
                <span className="text-xs text-muted-foreground">Карта на главной</span>
              </div>

              {geoIpStatus && !geoLoaded && (
                <p className="text-xs leading-relaxed text-muted-foreground">
                  Для офлайн-режима: GeoLite2 в <code className="text-foreground">data/geoip/</code>, затем перезапуск
                  панели.{' '}
                  <a
                    href="https://github.com/Kirito0098/AdminPanelAZ/blob/main/docs/GeoIP.md"
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary underline-offset-4 hover:underline"
                  >
                    Инструкция
                  </a>
                </p>
              )}

              {geoIpStatus && geoLoaded && (
                <div className="flex flex-wrap gap-1.5 text-[11px]">
                  <Badge variant={geoIpStatus.city_mmdb_exists ? 'outline' : 'secondary'}>City</Badge>
                  <Badge variant={geoIpStatus.asn_mmdb_exists ? 'outline' : 'secondary'}>ASN</Badge>
                </div>
              )}
            </CardContent>
          </Card>

          {settings && (
            <div className="rounded-xl border bg-muted/20 p-3">
              <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                Папка на сервере
              </p>
              <div className="flex items-center gap-2">
                <FolderOpen size={14} className="shrink-0 text-muted-foreground" />
                <code className="min-w-0 flex-1 truncate font-mono text-xs">{settings.antizapret_path}</code>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0"
                  onClick={() => void copyPath(settings.antizapret_path)}
                  title="Копировать путь"
                >
                  <Copy size={14} />
                </Button>
              </div>
            </div>
          )}
        </div>

        <SectionHeading
          title="Экстренный перезапуск"
          description="Выберите VPN-службу и перезапустите её вручную"
        />

        <Card className="overflow-hidden border-destructive/40 shadow-sm md:col-span-2">
          <div className="h-1 bg-gradient-to-r from-destructive/80 to-destructive/20" />
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base text-destructive">
              <ServerCrash size={18} />
              Перезапуск службы
            </CardTitle>
            <CardDescription>Только если обычное обновление не помогло</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-start gap-2 rounded-xl border border-destructive/20 bg-destructive/5 p-3 text-xs text-muted-foreground">
              <AlertTriangle size={14} className="mt-0.5 shrink-0 text-destructive" />
              <span>Все клиенты выбранной службы будут отключены на несколько секунд.</span>
            </div>

            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {SERVICES.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setService(s)}
                  className={cn(
                    'rounded-xl border px-3 py-2.5 text-left text-sm transition-all',
                    service === s
                      ? 'border-destructive bg-destructive/10 ring-1 ring-destructive/50'
                      : 'hover:border-muted-foreground/30 hover:bg-muted/40',
                  )}
                >
                  <span className="font-medium">{getVpnServiceLabel(s)}</span>
                </button>
              ))}
            </div>

            <Button
              className="w-full"
              variant="destructive"
              size="lg"
              disabled={!!busy}
              onClick={() => run('restart', `Перезапуск ${service}...`, () => restartService(service))}
            >
              <ServerCrash size={18} />
              {busy === 'restart' ? 'Перезапуск...' : `Перезапустить: ${getVpnServiceLabel(service)}`}
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
