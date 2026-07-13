import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import type { VisibleVpnProfilesPolicy } from '@/types'
import { cn } from '@/lib/utils'

export const FULL_VISIBLE_VPN_POLICY: VisibleVpnProfilesPolicy = {
  routes: ['az', 'vpn'],
  protocols: ['openvpn', 'wireguard', 'amneziawg'],
  openvpn_groups: ['udp_tcp', 'udp', 'tcp'],
}

const ROUTE_OPTIONS = [
  { key: 'az', label: 'AZ (AntiZapret)' },
  { key: 'vpn', label: 'VPN (полный)' },
] as const

const OPENVPN_GROUP_OPTIONS = [
  { key: 'udp_tcp', label: 'UDP+TCP' },
  { key: 'udp', label: 'UDP' },
  { key: 'tcp', label: 'TCP' },
] as const

const PROTOCOL_OPTIONS = [
  { key: 'openvpn', label: 'OpenVPN' },
  { key: 'wireguard', label: 'WireGuard' },
  { key: 'amneziawg', label: 'AmneziaWG' },
] as const

function toggleValue(list: string[], key: string, checked: boolean): string[] {
  if (checked) return list.includes(key) ? list : [...list, key]
  return list.filter((item) => item !== key)
}

export function isVisibleVpnPolicyEmpty(policy: VisibleVpnProfilesPolicy): boolean {
  if (!policy.routes.length || !policy.protocols.length) return true
  if (policy.protocols.includes('openvpn') && !policy.openvpn_groups.length) {
    return policy.protocols.every((p) => p === 'openvpn')
  }
  return false
}

export function copyVisibleVpnPolicy(policy?: VisibleVpnProfilesPolicy | null): VisibleVpnProfilesPolicy {
  const source = policy ?? FULL_VISIBLE_VPN_POLICY
  return {
    routes: [...source.routes],
    protocols: [...source.protocols],
    openvpn_groups: [...source.openvpn_groups],
  }
}

interface VpnVisibilityPolicyEditorProps {
  value: VisibleVpnProfilesPolicy
  onChange: (next: VisibleVpnProfilesPolicy) => void
  disabled?: boolean
  className?: string
}

export default function VpnVisibilityPolicyEditor({
  value,
  onChange,
  disabled = false,
  className,
}: VpnVisibilityPolicyEditorProps) {
  const empty = isVisibleVpnPolicyEmpty(value)

  const renderGroup = (
    title: string,
    options: readonly { key: string; label: string }[],
    axis: keyof VisibleVpnProfilesPolicy,
  ) => (
    <div className="space-y-2">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</p>
      <div className="flex flex-wrap gap-3">
        {options.map((option) => {
          const checked = value[axis].includes(option.key)
          return (
            <label key={option.key} className="inline-flex items-center gap-2 text-sm">
              <Checkbox
                checked={checked}
                disabled={disabled}
                onCheckedChange={(next) =>
                  onChange({
                    ...value,
                    [axis]: toggleValue(value[axis], option.key, next),
                  })
                }
              />
              {option.label}
            </label>
          )
        })}
      </div>
    </div>
  )

  return (
    <div className={cn('space-y-4', className)}>
      {renderGroup('Маршруты', ROUTE_OPTIONS, 'routes')}
      {renderGroup('OpenVPN группы', OPENVPN_GROUP_OPTIONS, 'openvpn_groups')}
      {renderGroup('Протоколы', PROTOCOL_OPTIONS, 'protocols')}
      {empty && (
        <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
          Пользователь не увидит ни одного профиля. Отметьте хотя бы маршрут и протокол.
        </p>
      )}
      {value.protocols.includes('openvpn') && value.openvpn_groups.length === 0 && (
        <p className="text-xs text-muted-foreground">
          OpenVPN выбран без групп — файлы OpenVPN будут скрыты.
        </p>
      )}
      <Label className="sr-only">Политика видимости VPN-профилей</Label>
    </div>
  )
}
