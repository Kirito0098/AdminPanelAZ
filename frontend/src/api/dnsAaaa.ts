import { apiFetch } from './http'
import type { DnsAaaaState, DnsAaaaTarget } from '@/types'

export async function getDnsAaaa(): Promise<DnsAaaaState> {
  return apiFetch<DnsAaaaState>('/dns-aaaa')
}

export async function setDnsAaaa(target: DnsAaaaTarget, nodata: boolean): Promise<DnsAaaaState> {
  return apiFetch<DnsAaaaState>('/dns-aaaa', {
    method: 'PUT',
    body: JSON.stringify({ target, nodata }),
  })
}
