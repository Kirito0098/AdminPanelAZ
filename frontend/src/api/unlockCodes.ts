import { apiFetch } from './http'
import type { UnlockCodeRecord } from '@/types'

export type UnlockCodeProtocol = 'openvpn' | 'wireguard' | 'amneziawg2'

export interface UnlockCodeCreateInput {
  grant_days: number
  protocols: UnlockCodeProtocol[]
  mode: 'single' | 'multi'
  max_redemptions?: number
  code_expires_at?: string | null
}

export interface UnlockCodeCreateResponse extends UnlockCodeRecord {}

export async function setClientAccessUntil(
  protocol: 'openvpn' | 'wireguard' | 'amneziawg2',
  clientName: string,
  accessUntil: string | null,
) {
  return apiFetch<{ access_until: string | null }>(`/client-access/${protocol}/${encodeURIComponent(clientName)}/access-until`, {
    method: 'PATCH',
    body: JSON.stringify({ access_until: accessUntil }),
  })
}

export async function getUnlockCodes(includeRevoked = false) {
  const params = new URLSearchParams()
  if (includeRevoked) params.set('include_revoked', 'true')
  const query = params.toString()
  return apiFetch<UnlockCodeRecord[]>(`/unlock-codes${query ? `?${query}` : ''}`)
}

export async function createUnlockCode(payload: UnlockCodeCreateInput) {
  return apiFetch<UnlockCodeCreateResponse>('/unlock-codes', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function revokeUnlockCode(codeId: number) {
  return apiFetch<{ ok: boolean; id: number }>(`/unlock-codes/${codeId}/revoke`, {
    method: 'POST',
  })
}
