import { apiFetch } from './http'
import type { DnsServersState } from '@/types'

export async function getDnsServers(): Promise<DnsServersState> {
  return apiFetch<DnsServersState>('/dns-servers')
}

export async function applyDnsServers(antizapret: number, vpn: number): Promise<DnsServersState> {
  return apiFetch<DnsServersState>('/dns-servers', {
    method: 'PUT',
    body: JSON.stringify({ antizapret, vpn }),
  })
}
