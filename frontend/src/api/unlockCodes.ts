import { apiFetch } from './http'
import type {
  ClientAccessUntilResponse,
  SyncClientAccessUntilResponse,
  UnlockCodeRecord,
} from '@/types'

export type UnlockCodeProtocol = 'openvpn' | 'wireguard' | 'amneziawg2'

export interface UnlockCodeCreateInput {
  grant_days: number
  protocols: UnlockCodeProtocol[]
  mode: 'single' | 'multi'
  max_redemptions?: number
  code_expires_at?: string | null
  allowed_client_names?: string[]
}

export type UnlockCodeCreateResponse = UnlockCodeRecord

export async function setClientAccessUntil(
  protocol: 'openvpn' | 'wireguard' | 'amneziawg2',
  clientName: string,
  accessUntil: string | null,
  confirmOverride = false,
) {
  return apiFetch<ClientAccessUntilResponse>(
    `/client-access/${protocol}/${encodeURIComponent(clientName)}/access-until`,
    {
      method: 'PATCH',
      body: JSON.stringify({ access_until: accessUntil, confirm_override: confirmOverride }),
    },
  )
}

export async function syncClientAccessUntilFromOwner(clientName: string) {
  return apiFetch<SyncClientAccessUntilResponse>(
    `/client-access/${encodeURIComponent(clientName)}/access-until/sync-from-owner`,
    {
      method: 'POST',
    },
  )
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
