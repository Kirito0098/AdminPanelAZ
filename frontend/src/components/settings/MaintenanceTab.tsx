import { useCallback, useEffect, useState } from 'react'
import { Database, FolderOpen, Globe, Play, RefreshCw, RotateCcw, ServerCrash } from 'lucide-react'
import { ApiError, getGeoIpStatus, getRetentionSettings, recreateProfiles, restartService, runDoall, updateRetentionSettings } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import type { AppSettings, GeoIpStatus, RetentionSettings } from '@/types'

const SERVICES = [
  'openvpn-server@antizapret-udp',
  'openvpn-server@antizapret-tcp',
  'openvpn-server@vpn-udp',
  'openvpn-server@vpn-tcp',
  'wg-quick@antizapret',
  'wg-quick@vpn',
]

interface MaintenanceTabProps {
  settings: AppSettings | null
}

export default function MaintenanceTab({ settings }: MaintenanceTabProps) {
  const { success, error: notifyError } = useNotifications()
  const { withInline, trackBackgroundTask } = useProgress()
  const [service, setService] = useState(SERVICES[0])
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

  const saveRetention = async () => {
    if (!retention) return
    setRetentionSaving(true)
    try {
      const updated = await updateRetentionSettings(retention)
      setRetention(updated)
      success('Настройки retention сохранены')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось сохранить retention')
    } finally {
      setRetentionSaving(false)
    }
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

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Play size={18} />
            Применение doall.sh
          </CardTitle>
          <CardDescription>
            Запуск doall.sh и пересоздание профилей клиентов на активном узле
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <SettingsAlert variant="warning" title="Длительная операция">
            doall.sh может занять несколько минут. Прогресс отображается в верхней полосе задачи.
          </SettingsAlert>
          <Button
            variant="secondary"
            disabled={!!busy}
            onClick={async () => {
              setBusy('doall')
              try {
                const resp = await runDoall()
                trackBackgroundTask(resp.task_id, {
                  onComplete: () => success(resp.message || 'doall.sh выполнен'),
                  onError: (task, message) => notifyError(task?.error || task?.message || message),
                })
              } catch (err) {
                notifyError(err instanceof ApiError ? err.message : 'Ошибка запуска doall')
              } finally {
                setBusy(null)
              }
            }}
          >
            <Play size={16} className={busy === 'doall' ? 'animate-spin' : ''} />
            Запустить doall.sh
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Play size={18} />
            Профили клиентов
          </CardTitle>
          <CardDescription>
            Пересоздание профилей клиентов (client.sh 7). Применение doall.sh — в разделе «Маршрутизация / CIDR» или «Редактор файлов».
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <SettingsAlert variant="warning" title="Влияние на клиентов">
            Пересоздание профилей может занять время и затронуть активные подключения. Выполняйте в период низкой нагрузки.
          </SettingsAlert>
          <Button
            variant="secondary"
            disabled={!!busy}
            onClick={() => run('recreate', 'Пересоздание профилей...', recreateProfiles)}
          >
            <RotateCcw size={16} className={busy === 'recreate' ? 'animate-spin' : ''} />
            Пересоздать профили
          </Button>
        </CardContent>
      </Card>

      {retention && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Database size={18} />
              Retention (очистка БД)
            </CardTitle>
            <CardDescription>
              Автоматическое удаление старых traffic samples, action logs и resource metrics
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <div className="flex items-center justify-between rounded-lg border p-3 md:col-span-2">
              <div>
                <div className="font-medium">Фоновая очистка</div>
                <div className="text-xs text-muted-foreground">Batch DELETE по расписанию</div>
              </div>
              <Switch
                checked={retention.enabled}
                onCheckedChange={(checked) => setRetention({ ...retention, enabled: checked })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="retention-interval">Интервал (часы)</Label>
              <Input
                id="retention-interval"
                type="number"
                min={1}
                max={168}
                value={retention.interval_hours}
                onChange={(e) => setRetention({ ...retention, interval_hours: Number(e.target.value) })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="retention-traffic">Traffic samples (дней)</Label>
              <Input
                id="retention-traffic"
                type="number"
                min={1}
                value={retention.traffic_sample_retention_days}
                onChange={(e) =>
                  setRetention({ ...retention, traffic_sample_retention_days: Number(e.target.value) })
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="retention-logs">Action logs (дней)</Label>
              <Input
                id="retention-logs"
                type="number"
                min={1}
                value={retention.action_log_retention_days}
                onChange={(e) => setRetention({ ...retention, action_log_retention_days: Number(e.target.value) })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="retention-node-metrics">Node metrics (дней)</Label>
              <Input
                id="retention-node-metrics"
                type="number"
                min={1}
                value={retention.resource_metrics_retention_days}
                onChange={(e) =>
                  setRetention({ ...retention, resource_metrics_retention_days: Number(e.target.value) })
                }
              />
            </div>
            <Button type="button" disabled={retentionSaving} onClick={() => void saveRetention()}>
              Сохранить retention
            </Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Globe size={18} />
            GeoIP
          </CardTitle>
          <CardDescription>
            Локальная MaxMind GeoLite2 для NOC без ip-api.com.{' '}
            <a
              href="https://github.com/Kirito0098/AdminPanelAZ/blob/main/docs/GeoIP.md"
              target="_blank"
              rel="noreferrer"
              className="text-primary underline-offset-4 hover:underline"
            >
              Инструкция по загрузке MMDB
            </a>{' '}
            (на сервере: <code className="mono text-xs">docs/GeoIP.md</code>)
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            {geoIpStatus ? (
              <Badge variant={geoIpStatus.loaded ? 'default' : 'secondary'}>
                GeoIP: {geoIpStatus.loaded ? 'локальная база' : 'резерв ip-api'}
              </Badge>
            ) : (
              <Badge variant="outline">GeoIP: статус неизвестен</Badge>
            )}
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={geoIpLoading}
              onClick={() => void loadGeoIpStatus()}
            >
              <RefreshCw size={14} className={geoIpLoading ? 'animate-spin' : ''} />
              Обновить статус
            </Button>
          </div>
          {geoIpStatus && (
            <div className="space-y-2 text-xs text-muted-foreground">
              <div>
                City (MMDB):{' '}
                <code className="mono rounded bg-muted px-1 py-0.5">{geoIpStatus.city_mmdb_path ?? '—'}</code>{' '}
                ({geoIpStatus.city_mmdb_exists ? 'файл найден' : 'файл не найден'})
              </div>
              <div>
                ASN (MMDB):{' '}
                <code className="mono rounded bg-muted px-1 py-0.5">{geoIpStatus.asn_mmdb_path ?? '—'}</code>{' '}
                ({geoIpStatus.asn_mmdb_exists ? 'файл найден' : 'файл не найден'})
              </div>
            </div>
          )}
          {geoIpStatus && !geoIpStatus.loaded && (
            <SettingsAlert variant="warning" title="Резервный ip-api">
              Положите GeoLite2-City.mmdb (и опционально GeoLite2-ASN.mmdb) в data/geoip/ и перезапустите панель.
            </SettingsAlert>
          )}
        </CardContent>
      </Card>

      {settings && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FolderOpen size={18} />
              Путь AntiZapret
            </CardTitle>
            <CardDescription>Корневая директория на активном узле (только чтение)</CardDescription>
          </CardHeader>
          <CardContent>
            <code className="mono block w-full overflow-x-auto rounded-md bg-muted px-3 py-2 text-xs">
              {settings.antizapret_path}
            </code>
          </CardContent>
        </Card>
      )}

      <Card className="border-destructive/20">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base text-destructive">
            <ServerCrash size={18} />
            Перезапуск служб VPN
          </CardTitle>
          <CardDescription>systemctl restart на активном узле — кратковременный обрыв соединений</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <SettingsAlert variant="danger" title="Опасная операция">
            Перезапуск службы прервёт активные VPN-сессии всех клиентов, подключённых через выбранный сервис.
          </SettingsAlert>
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[240px] flex-1 space-y-2">
              <Label htmlFor="service-select">Служба</Label>
              <Select value={service} onValueChange={setService}>
                <SelectTrigger id="service-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SERVICES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              variant="destructive"
              disabled={!!busy}
              onClick={() => run('restart', `Перезапуск ${service}...`, () => restartService(service))}
            >
              Перезапустить
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
