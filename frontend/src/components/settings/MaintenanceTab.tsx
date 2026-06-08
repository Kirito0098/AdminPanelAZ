import { useState } from 'react'
import { Play, RotateCcw, ServerCrash } from 'lucide-react'
import { ApiError, recreateProfiles, restartService, runDoall } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'

const SERVICES = [
  'openvpn-server@antizapret-udp',
  'openvpn-server@antizapret-tcp',
  'openvpn-server@vpn-udp',
  'openvpn-server@vpn-tcp',
  'wg-quick@antizapret',
  'wg-quick@vpn',
]

export default function MaintenanceTab() {
  const { success, error: notifyError } = useNotifications()
  const { inline, withInline, trackBackgroundTask, backgroundTaskPolling } = useProgress()
  const [service, setService] = useState(SERVICES[0])
  const [busy, setBusy] = useState<string | null>(null)

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
      <InlineProgressBar active={inline.active || backgroundTaskPolling} label={inline.label} />

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
