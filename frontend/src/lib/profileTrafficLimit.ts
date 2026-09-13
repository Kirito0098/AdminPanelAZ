import {
  awg2ClearTrafficLimit,
  awg2SetTrafficLimit,
  openvpnClearTrafficLimit,
  openvpnSetTrafficLimit,
  wgClearTrafficLimit,
  wgSetTrafficLimit,
} from '@/api/vpnAccess'
import type { VpnType } from '@/types'

export const PROFILE_VPN_ORDER: VpnType[] = ['openvpn', 'wireguard', 'amneziawg2']

export type TrafficLimitSetter = (
  clientName: string,
  limitValue: number,
  limitUnit: string,
  limitPeriodDays?: number | null,
) => Promise<unknown>

export type TrafficLimitClearer = (clientName: string) => Promise<unknown>

const DEFAULT_SETTERS: Record<VpnType, TrafficLimitSetter> = {
  openvpn: openvpnSetTrafficLimit,
  wireguard: wgSetTrafficLimit,
  amneziawg2: awg2SetTrafficLimit,
}

const DEFAULT_CLEARERS: Record<VpnType, TrafficLimitClearer> = {
  openvpn: openvpnClearTrafficLimit,
  wireguard: wgClearTrafficLimit,
  amneziawg2: awg2ClearTrafficLimit,
}

export function orderedProfileProtocols(protocols: Iterable<VpnType>): VpnType[] {
  const set = new Set(protocols)
  return PROFILE_VPN_ORDER.filter((protocol) => set.has(protocol))
}

export async function setProfileTrafficLimits(
  clientName: string,
  protocols: Iterable<VpnType>,
  value: number,
  unit: string,
  periodDays: number | null,
  setters: Partial<Record<VpnType, TrafficLimitSetter>> = {},
): Promise<{ applied: VpnType[]; failed: Array<{ protocol: VpnType; message: string }> }> {
  const applied: VpnType[] = []
  const failed: Array<{ protocol: VpnType; message: string }> = []
  for (const protocol of orderedProfileProtocols(protocols)) {
    const setter = setters[protocol] ?? DEFAULT_SETTERS[protocol]
    try {
      await setter(clientName, value, unit, periodDays)
      applied.push(protocol)
    } catch (err) {
      failed.push({
        protocol,
        message: err instanceof Error ? err.message : 'ошибка',
      })
    }
  }
  return { applied, failed }
}

export async function clearProfileTrafficLimits(
  clientName: string,
  protocols: Iterable<VpnType>,
  clearers: Partial<Record<VpnType, TrafficLimitClearer>> = {},
): Promise<{ cleared: VpnType[]; failed: Array<{ protocol: VpnType; message: string }> }> {
  const cleared: VpnType[] = []
  const failed: Array<{ protocol: VpnType; message: string }> = []
  for (const protocol of orderedProfileProtocols(protocols)) {
    const clearer = clearers[protocol] ?? DEFAULT_CLEARERS[protocol]
    try {
      await clearer(clientName)
      cleared.push(protocol)
    } catch (err) {
      failed.push({
        protocol,
        message: err instanceof Error ? err.message : 'ошибка',
      })
    }
  }
  return { cleared, failed }
}

export function formatProfileProtocols(protocols: Iterable<VpnType>): string {
  const labels: Record<VpnType, string> = {
    openvpn: 'OpenVPN',
    wireguard: 'WireGuard',
    amneziawg2: 'AmneziaWG 2.0',
  }
  return orderedProfileProtocols(protocols)
    .map((protocol) => labels[protocol])
    .join(', ')
}
