import {
  apiFetch,
  apiFetchResponse,
} from './http'
import type {
  QrDownloadAuditEntry,
  OpenVpnSocketStatus,
  ActionLogEntry,
  ConnectionLogsSnapshot,
  OpenVpnEventProfile,
} from '../types'

export async function getQrDownloadLogs(limit = 50) {
  return apiFetch<QrDownloadAuditEntry[]>(`/logs/qr-downloads?limit=${limit}`)
}

export async function getOpenVpnSockets() {
  return apiFetch<{ sockets: OpenVpnSocketStatus[]; timestamp: string }>(
    '/logs/openvpn-sockets',
  )
}

export async function getActionLogs(limit = 100) {
  return apiFetch<ActionLogEntry[]>(`/logs/actions?limit=${limit}`)
}

export function downloadActionLogsExport() {
  return apiFetchResponse('/logs/action-logs/export')
}

export async function getConnectionLogs() {
  return apiFetch<ConnectionLogsSnapshot>('/logs/connections')
}

export async function getOpenVpnEvents() {
  return apiFetch<{ profiles: OpenVpnEventProfile[]; timestamp: string }>('/logs/openvpn-events')
}
