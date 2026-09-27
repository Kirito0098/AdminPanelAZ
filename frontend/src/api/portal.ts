import { apiFetch } from './http'
import type { PortalLinkResponse } from '@/types'

export interface PortalFileMeta {
  path: string
  label: string
  filename: string
  vpn_type: string
  download_url: string
  openvpn_import_url?: string
}

export interface PortalStatusMeta {
  status: 'active' | 'expired' | 'blocked' | string
  status_label: string
  expires_at: string | null
  expires_label: string
  traffic_used_bytes: number
  traffic_limit_bytes: number | null
  traffic_label: string
}

export interface PortalClientEntry {
  node_id: number
  client_name: string
  protocols: string[]
  files: PortalFileMeta[]
  status?: PortalStatusMeta
}

export interface ClientPortalMetaResponse extends PortalClientEntry {
  kind?: 'client'
  brand_title: string
  unlock_codes_enabled: boolean
}

export interface UserPortalMetaResponse {
  kind: 'user'
  brand_title: string
  unlock_codes_enabled: boolean
  clients: PortalClientEntry[]
}

export type PortalMetaResponse = ClientPortalMetaResponse | UserPortalMetaResponse

export interface PortalRedeemResponse {
  ok: boolean
  grant_days: number
  protocols_applied: string[]
  access_until: string | null
  access_until_by_protocol?: Record<string, string | null>
}

export async function getPortalLink(clientName: string) {
  return apiFetch<PortalLinkResponse>(`/portal/clients/${encodeURIComponent(clientName)}/link`)
}

export async function createPortalLink(clientName: string) {
  return apiFetch<PortalLinkResponse>(`/portal/clients/${encodeURIComponent(clientName)}/link`, {
    method: 'POST',
  })
}

export async function rotatePortalLink(clientName: string) {
  return apiFetch<PortalLinkResponse>(`/portal/clients/${encodeURIComponent(clientName)}/rotate`, {
    method: 'POST',
  })
}

export async function revokePortalLink(clientName: string) {
  return apiFetch<{ ok: boolean; client_name: string }>(
    `/portal/clients/${encodeURIComponent(clientName)}/revoke`,
    { method: 'POST' },
  )
}

export async function getUserPortalLink(userId: number) {
  return apiFetch<PortalLinkResponse>(`/portal/users/${userId}/link`)
}

export async function createUserPortalLink(userId: number) {
  return apiFetch<PortalLinkResponse>(`/portal/users/${userId}/link`, {
    method: 'POST',
  })
}

export async function rotateUserPortalLink(userId: number) {
  return apiFetch<PortalLinkResponse>(`/portal/users/${userId}/rotate`, {
    method: 'POST',
  })
}

export async function revokeUserPortalLink(userId: number) {
  return apiFetch<{ ok: boolean; user_id: number }>(`/portal/users/${userId}/revoke`, {
    method: 'POST',
  })
}

/** Public portal meta — called from /p/:token without auth. */
export async function fetchPublicPortalMeta(token: string) {
  const { apiBase } = await import('../lib/panelBase')
  const res = await fetch(`${apiBase}/public/portal/${encodeURIComponent(token)}`, {
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) {
    let detail = 'Не удалось загрузить страницу'
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return (await res.json()) as PortalMetaResponse
}

export async function redeemPublicPortalCode(token: string, code: string) {
  const { apiBase } = await import('../lib/panelBase')
  const res = await fetch(`${apiBase}/public/portal/${encodeURIComponent(token)}/redeem`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ code }),
  })
  if (!res.ok) {
    let detail = 'Не удалось активировать ключ'
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return (await res.json()) as PortalRedeemResponse
}
