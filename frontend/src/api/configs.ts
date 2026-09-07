import { getWebSessionId } from '@/lib/webSession'
import {
  API_BASE,
  apiFetch,
  getToken,
  parseApiError,
  refreshAccessToken,
} from './http'

export async function getConfigs(includeFiles = false, tagIds?: number[]) {
  const params = new URLSearchParams()
  if (includeFiles) params.set('include_files', 'true')
  if (tagIds?.length) tagIds.forEach((id) => params.append('tag_ids', String(id)))
  const query = params.toString() ? `?${params.toString()}` : ''
  return apiFetch<import('../types').VpnConfig[]>(`/configs${query}`)
}

export async function getConfigQuota() {
  return apiFetch<import('../types').SelfServiceQuota>('/configs/quota')
}

export async function getEffectiveVisibleVpnProfiles() {
  return apiFetch<import('../types').EffectiveVisibleVpnProfilesResponse>('/configs/visible-vpn-profiles')
}

export async function getUserVpnVisibilityDefault() {
  return apiFetch<import('../types').VisibleVpnProfilesDefaultResponse>(
    '/settings/user-vpn-visibility-default',
  )
}

export async function setUserVpnVisibilityDefault(policy: import('../types').VisibleVpnProfilesPolicy) {
  return apiFetch<import('../types').VisibleVpnProfilesDefaultResponse>(
    '/settings/user-vpn-visibility-default',
    {
      method: 'PUT',
      body: JSON.stringify({ policy }),
    },
  )
}

export async function getConfigProfileFiles(ids?: number[]) {
  const query = ids?.length ? `?ids=${ids.join(',')}` : ''
  return apiFetch<Record<string, import('../types').VpnConfig['profile_files']>>(
    `/configs/profile-files${query}`,
  )
}

export async function createConfig(data: {
  client_name: string
  vpn_type: import('../types').VpnType
  cert_expire_days?: number
  ttl?: string
  description?: string
  owner_id?: number
}) {
  return apiFetch<import('../types').VpnConfig>('/configs', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function deleteConfig(id: number) {
  return apiFetch(`/configs/${id}`, { method: 'DELETE' })
}

export async function updateConfig(
  id: number,
  data: { description?: string; cert_expire_days?: number; owner_id?: number },
) {
  return apiFetch<import('../types').VpnConfig>(`/configs/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function syncConfigs() {
  return apiFetch<{ message: string }>('/configs/sync', { method: 'POST' })
}

export async function getConfigTags() {
  return apiFetch<import('../types').ConfigTag[]>('/config-tags')
}

export async function createConfigTag(data: { name: string; color?: string }) {
  return apiFetch<import('../types').ConfigTag>('/config-tags', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function deleteConfigTag(id: number) {
  return apiFetch(`/config-tags/${id}`, { method: 'DELETE' })
}

export async function setConfigTags(configId: number, tagIds: number[]) {
  return apiFetch<import('../types').ConfigTag[]>(`/config-tags/configs/${configId}/tags`, {
    method: 'PUT',
    body: JSON.stringify({ tag_ids: tagIds }),
  })
}

export async function getClientTemplates() {
  return apiFetch<import('../types').ClientTemplate[]>('/client-templates')
}

export async function applyClientTemplate(
  templateId: number,
  data: { client_name: string; owner_id?: number },
) {
  return apiFetch<import('../types').VpnConfig>(`/client-templates/${templateId}/apply`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function bulkConfigOp(data: {
  operation: 'block_temp' | 'block_perm' | 'unblock' | 'delete' | 'renew_cert' | 'change_owner'
  config_ids?: number[]
  tag_ids?: number[]
  block_days?: number
  renew_cert_days?: number
  owner_id?: number
}) {
  return apiFetch<{ task_id: string; queued: boolean; status_url: string }>('/configs/bulk', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function downloadProfile(configId: number, path: string) {
  const token = getToken()
  const url = `${API_BASE}/configs/${configId}/download?path=${encodeURIComponent(path)}`
  return fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
}

export function downloadConfigsExport() {
  const token = getToken()
  return fetch(`${API_BASE}/configs/export`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: 'include',
  })
}

export async function importConfigsCsv(file: File) {
  const form = new FormData()
  form.append('file', file)
  return apiFetch<import('../types').ConfigCsvImportResponse>('/configs/import', {
    method: 'POST',
    body: form,
  })
}

export async function createOneTimeLink(configId: number, path: string) {
  const params = new URLSearchParams({ path })
  return apiFetch<import('../types').OneTimeLinkResponse>(
    `/configs/${configId}/one-time-link?${params}`,
    { method: 'POST' },
  )
}

export type QrContentMode = 'profile' | 'download-link'

export type QrBlobResult = {
  blob: Blob
  contentMode: QrContentMode
  downloadUrl?: string
}

export async function fetchQrBlob(
  configId: number,
  path: string,
  retry = true,
): Promise<QrBlobResult> {
  const headers = new Headers()
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const sessionId = getWebSessionId()
  if (sessionId) headers.set('X-Web-Session-Id', sessionId)

  const params = new URLSearchParams({ path })
  const response = await fetch(`${API_BASE}/configs/${configId}/qr?${params}`, {
    headers,
    credentials: 'include',
  })
  if (response.status === 401 && retry) {
    const newToken = await refreshAccessToken()
    if (newToken) {
      return fetchQrBlob(configId, path, false)
    }
    localStorage.removeItem('token')
  }
  if (!response.ok) {
    throw await parseApiError(response, 'Ошибка генерации QR')
  }
  const contentMode: QrContentMode =
    response.headers.get('X-Qr-Content') === 'download-link' ? 'download-link' : 'profile'
  const downloadUrl = response.headers.get('X-Qr-Download-Url') ?? undefined
  return { blob: await response.blob(), contentMode, downloadUrl }
}
