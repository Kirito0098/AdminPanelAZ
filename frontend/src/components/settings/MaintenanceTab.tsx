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
import { getVpnServiceLabel } from '@/components/settings/settingsLabels'
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
      success('Настройки очистки сохранены')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось сохранить настройки очистки')
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
            Полное обновление VPN
          </CardTitle>
          <CardDescription>
            Применить все изменения маршрутизации и пересоздать профили клиентов на сервере
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <SettingsAlert variant="warning" title="Может занять несколько минут">
            Во время операции VPN может быть недоступен. Прогресс отображается в верхней полосе.
          </SettingsAlert>
          <Button
            variant="secondary"
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
            <Play size={16} className={busy === 'doall' ? 'animate-spin' : ''} />
            Запустить полное обновление
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
            Обновить файлы подключения у всех VPN-клиентов. Полное обновление — в разделе «Маршрутизация» или «Редактор файлов».
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
              Очистка старых данных
            </CardTitle>
            <CardDescription>
              Автоматически удалять устаревшую статистику трафика, журналы и метрики сервера
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <div className="flex items-center justify-between rounded-lg border p-3 md:col-span-2">
              <div>
                <div className="font-medium">Автоматическая очистка</div>
                <div className="text-xs text-muted-foreground">Удалять старые записи по расписанию</div>
              </div>
              <Switch
                checked={retention.enabled}
                onCheckedChange={(checked) => setRetention({ ...retention, enabled: checked })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="retention-interval">Как часто проверять (часы)</Label>
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
              <Label htmlFor="retention-traffic">Хранить статистику трафика (дней)</Label>
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
              <Label htmlFor="retention-logs">Хранить журнал действий (дней)</Label>
              <Input
                id="retention-logs"
                type="number"
                min={1}
                value={retention.action_log_retention_days}
                onChange={(e) => setRetention({ ...retention, action_log_retention_days: Number(e.target.value) })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="retention-node-metrics">Хранить метрики сервера (дней)</Label>
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
              Сохранить настройки очистки
            </Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Globe size={18} />
            Определение страны по IP
          </CardTitle>
          <CardDescription>
            Локальная база геолокации для карты подключений.{' '}
            <a
              href="https://github.com/Kirito0098/AdminPanelAZ/blob/main/docs/GeoIP.md"
              target="_blank"
              rel="noreferrer"
              className="text-primary underline-offset-4 hover:underline"
            >
              Как установить базу
            </a>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            {geoIpStatus ? (
              <Badge variant={geoIpStatus.loaded ? 'default' : 'secondary'}>
                {geoIpStatus.loaded ? 'Локальная база установлена' : 'Используется резервный сервис'}
              </Badge>
            ) : (
              <Badge variant="outline">Статус неизвестен</Badge>
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
            <SettingsAlert variant="warning" title="База не установлена">
              Положите файлы GeoLite2 в папку data/geoip/ на сервере и перезапустите панель.
            </SettingsAlert>
          )}
        </CardContent>
      </Card>

      {settings && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FolderOpen size={18} />
              Папка AntiZapret на сервере
            </CardTitle>
            <CardDescription>Расположение файлов VPN — только для просмотра</CardDescription>
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
          <CardDescription>Кратковременно прервёт VPN-подключения выбранной службы</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <SettingsAlert variant="danger" title="Опасная операция">
            Перезапуск службы прервёт активные VPN-сессии всех клиентов, подключённых через выбранный сервис.
          </SettingsAlert>
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[240px] flex-1 space-y-2">
              <Label htmlFor="service-select">Какую службу перезапустить</Label>
              <Select value={service} onValueChange={setService}>
                <SelectTrigger id="service-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SERVICES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {getVpnServiceLabel(s)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground font-mono">{service}</p>
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
