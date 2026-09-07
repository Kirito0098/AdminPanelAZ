import {
  API_BASE,
  apiFetch,
  getToken,
} from './http'

export async function getQrDownloadLogs(limit = 50) {
  return apiFetch<import('../types').QrDownloadAuditEntry[]>(`/logs/qr-downloads?limit=${limit}`)
}

export async function getOpenVpnSockets() {
  return apiFetch<{ sockets: import('../types').OpenVpnSocketStatus[]; timestamp: string }>(
    '/logs/openvpn-sockets',
  )
}

export async function getActionLogs(limit = 100) {
  return apiFetch<import('../types').ActionLogEntry[]>(`/logs/actions?limit=${limit}`)
}

export function downloadActionLogsExport() {
  const token = getToken()
  return fetch(`${API_BASE}/logs/action-logs/export`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: 'include',
  })
}

export async function getConnectionLogs() {
  return apiFetch<import('../types').ConnectionLogsSnapshot>('/logs/connections')
}

export async function getOpenVpnEvents() {
  return apiFetch<{ profiles: import('../types').OpenVpnEventProfile[]; timestamp: string }>('/logs/openvpn-events')
}
