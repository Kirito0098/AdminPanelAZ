import { Activity, Power, RefreshCw } from 'lucide-react'
import { postWarperToggle } from '@/api/client'
import StatusPanel from '@/components/noc/StatusPanel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useNotifications } from '@/context/NotificationContext'
import type { Node, WarperHealthResponse, WarperStatusResponse } from '@/types'
import WarperAlerts from './WarperAlerts'
import { formatNodeLabel } from './utils'

interface StatusSectionProps {
  health: WarperHealthResponse | null
  status: WarperStatusResponse | null
  loading: boolean
  loadError: string | null
  activeNode: Node | null
  onRefresh: () => void
  onToggled: () => void
}

function readString(obj: Record<string, unknown> | undefined, key: string): string | null {
  const value = obj?.[key]
  return typeof value === 'string' ? value : null
}

function readNested(obj: Record<string, unknown> | undefined, ...keys: string[]): unknown {
  let current: unknown = obj
  for (const key of keys) {
    if (!current || typeof current !== 'object') return null
    current = (current as Record<string, unknown>)[key]
  }
  return current
}

export default function StatusSection({
  health,
  status,
  loading,
  loadError,
  activeNode,
  onRefresh,
  onToggled,
}: StatusSectionProps) {
  const { success, error: notifyError } = useNotifications()
  const statusData = status?.status ?? {}
  const outboundMode = readString(statusData, 'outbound_mode')
  const singbox = readNested(statusData, 'singbox') as Record<string, unknown> | null
  const fakeSubnet = readString(statusData, 'fake_subnet')
  const nodeLabel = formatNodeLabel(health, activeNode)

  async function handleToggle() {
    try {
      const result = await postWarperToggle()
      success(result.message ?? 'AZ-WARP переключён')
      onToggled()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось переключить AZ-WARP')
    }
  }

  return (
    <div className="space-y-4">
      <WarperAlerts health={health} activeNode={activeNode} loadError={loadError} />

      <StatusPanel title="Детальный статус" icon={Activity}>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Badge variant="outline">Узел: {nodeLabel}</Badge>
          {health && (
            <Badge variant={health.installed ? 'secondary' : 'outline'}>
              {health.installed ? 'Установлен' : 'Не установлен'}
            </Badge>
          )}
          {health?.installed && (
            <Badge variant={health.active ? 'default' : 'secondary'}>
              {health.active ? 'Активен' : 'Выключен'}
            </Badge>
          )}
          {health?.version && <Badge variant="outline">v{health.version}</Badge>}
          {outboundMode && <Badge variant="outline">Режим: {outboundMode}</Badge>}
        </div>

        <dl className="mb-4 grid gap-3 text-sm sm:grid-cols-2">
          {fakeSubnet && (
            <div className="rounded-lg border p-3">
              <dt className="text-muted-foreground">Fake-подсеть</dt>
              <dd className="mt-1 font-mono">{fakeSubnet}</dd>
            </div>
          )}
          {singbox && typeof singbox.mtu === 'number' && (
            <div className="rounded-lg border p-3">
              <dt className="text-muted-foreground">MTU sing-box</dt>
              <dd className="mt-1">{singbox.mtu}</dd>
            </div>
          )}
          {singbox && typeof singbox.running === 'boolean' && (
            <div className="rounded-lg border p-3">
              <dt className="text-muted-foreground">sing-box</dt>
              <dd className="mt-1">{singbox.running ? 'Запущен' : 'Остановлен'}</dd>
            </div>
          )}
          {health?.health_error && (
            <div className="rounded-lg border border-destructive/30 p-3 sm:col-span-2">
              <dt className="text-muted-foreground">Ошибка health</dt>
              <dd className="mt-1 text-destructive">{health.health_error}</dd>
            </div>
          )}
        </dl>

        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="secondary" size="sm" onClick={onRefresh} disabled={loading}>
            <RefreshCw className={`mr-1.5 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Обновить
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={() => void handleToggle()}
            disabled={loading || !health?.installed || health.conflict_antizapret_warp}
          >
            <Power className="mr-1.5 h-4 w-4" />
            Вкл / выкл
          </Button>
        </div>
      </StatusPanel>
    </div>
  )
}
