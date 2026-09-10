import { apiFetch } from './http'

export interface PortalLinkResponse {
  token: string
  client_name: string
  url: string
  revoked: boolean
}

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

export interface PortalMetaResponse {
  client_name: string
  brand_title: string
  protocols: string[]
  files: PortalFileMeta[]
  status?: PortalStatusMeta
}

export interface PortalRedeemResponse {
  ok: boolean
  grant_days: number
  protocols_applied: string[]
  access_until: string | null
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
