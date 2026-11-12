import { Badge } from '@/components/ui/badge'
import type { Node, WarperHealthResponse, WarperStatusResponse } from '@/types'
import { formatNodeLabel, formatOutboundMode } from './utils'

interface StatusSectionProps {
  health: WarperHealthResponse | null
  status: WarperStatusResponse | null
  activeNode: Node | null
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

function readBoolean(obj: Record<string, unknown> | undefined, key: string): boolean | null {
  const value = obj?.[key]
  return typeof value === 'boolean' ? value : null
}

export default function StatusSection({ health, status, activeNode }: StatusSectionProps) {
  const statusData = status?.status ?? {}
  const outboundMode = readString(statusData, 'outbound_mode')
  const singbox = readNested(statusData, 'singbox') as Record<string, unknown> | null
  const kresd = readNested(statusData, 'kresd') as Record<string, unknown> | null
  const subnetBlock = readNested(statusData, 'subnet') as Record<string, unknown> | null
  // status JSON хранит подсеть в subnet.fake; поддерживаем и плоский fake_subnet как fallback.
  const fakeSubnet =
    (subnetBlock && typeof subnetBlock.fake === 'string' ? (subnetBlock.fake as string) : null) ??
    readString(statusData, 'fake_subnet') ??
    readString(statusData, 'subnet')
  const logLevel =
    (singbox && typeof singbox.log_level === 'string' ? (singbox.log_level as string) : null) ??
    readString(statusData, 'log_level')
  const fullVpnRaw = statusData?.['fullvpn_warp_resolve']
  const fullVpn =
    typeof fullVpnRaw === 'boolean'
      ? fullVpnRaw
      : typeof fullVpnRaw === 'string'
        ? ['y', 'yes', '1', 'true', 'on'].includes(fullVpnRaw.trim().toLowerCase())
        : readBoolean(statusData, 'fullvpn')
  const kresdPatched = kresd && typeof kresd.patched === 'boolean' ? kresd.patched : null
  const nodeLabel = formatNodeLabel(health, activeNode)

  return (
    <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
      <div className="rounded-lg border bg-muted/20 p-3 xl:col-span-2">
        <dt className="text-xs text-muted-foreground">Узел</dt>
        <dd className="mt-1 truncate text-sm font-medium" title={nodeLabel}>
          {nodeLabel}
        </dd>
      </div>
      {outboundMode && (
        <div className="rounded-lg border bg-muted/20 p-3">
          <dt className="text-xs text-muted-foreground">Режим выхода</dt>
          <dd className="mt-1 text-sm font-medium">{formatOutboundMode(outboundMode)}</dd>
        </div>
      )}
      {fakeSubnet && (
        <div className="rounded-lg border bg-muted/20 p-3">
          <dt className="text-xs text-muted-foreground">Fake-подсеть</dt>
          <dd className="mt-1 font-mono text-sm">{fakeSubnet}</dd>
        </div>
      )}
      {singbox && typeof singbox.mtu === 'number' && (
        <div className="rounded-lg border bg-muted/20 p-3">
          <dt className="text-xs text-muted-foreground">MTU sing-box</dt>
          <dd className="mt-1 text-sm font-medium">{singbox.mtu}</dd>
        </div>
      )}
      {singbox && typeof singbox.running === 'boolean' && (
        <div className="rounded-lg border bg-muted/20 p-3">
          <dt className="text-xs text-muted-foreground">sing-box</dt>
          <dd className="mt-1">
            <Badge variant={singbox.running ? 'success' : 'secondary'}>
              {singbox.running ? 'Запущен' : 'Остановлен'}
            </Badge>
          </dd>
        </div>
      )}
      {kresdPatched != null && (
        <div className="rounded-lg border bg-muted/20 p-3">
          <dt className="text-xs text-muted-foreground">kresd</dt>
          <dd className="mt-1">
            <Badge variant={kresdPatched ? 'success' : 'secondary'}>
              {kresdPatched ? 'Пропатчен' : 'Не пропатчен'}
            </Badge>
          </dd>
        </div>
      )}
      {fullVpn != null && (
        <div className="rounded-lg border bg-muted/20 p-3">
          <dt className="text-xs text-muted-foreground">FullVPN</dt>
          <dd className="mt-1 text-sm font-medium">{fullVpn ? 'Включён' : 'Выключен'}</dd>
        </div>
      )}
      {logLevel && (
        <div className="rounded-lg border bg-muted/20 p-3">
          <dt className="text-xs text-muted-foreground">Уровень логов</dt>
          <dd className="mt-1 font-mono text-sm uppercase">{logLevel}</dd>
        </div>
      )}
      {health?.health_error && (
        <div className="rounded-lg border border-destructive/30 p-3 sm:col-span-2 lg:col-span-full">
          <dt className="text-muted-foreground">Ошибка health</dt>
          <dd className="mt-1 text-destructive">{health.health_error}</dd>
        </div>
      )}
    </dl>
  )
}
