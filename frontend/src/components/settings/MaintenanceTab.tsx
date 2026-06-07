import { useState } from 'react'
import { Play, RefreshCw, RotateCcw } from 'lucide-react'
import { ApiError, recreateProfiles, restartService, runDoall } from '@/api/client'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
  const { inline, withInline } = useProgress()
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
      <InlineProgressBar active={inline.active} label={inline.label} />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Play size={18} />
            Обслуживание AntiZapret
          </CardTitle>
          <CardDescription>Запуск doall.sh и пересоздание профилей клиентов (client.sh 7)</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            disabled={!!busy}
            onClick={() => run('doall', 'Выполнение doall.sh...', runDoall)}
          >
            <RefreshCw size={16} className={busy === 'doall' ? 'animate-spin' : ''} />
            Запустить doall.sh
          </Button>
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

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Перезапуск служб VPN</CardTitle>
          <CardDescription>systemctl restart на активном узле</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          <div className="min-w-[240px] flex-1 space-y-2">
            <Select value={service} onValueChange={setService}>
              <SelectTrigger>
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
            disabled={!!busy}
            onClick={() => run('restart', `Перезапуск ${service}...`, () => restartService(service))}
          >
            Перезапустить
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
