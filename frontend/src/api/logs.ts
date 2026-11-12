import {
  apiFetch,
  apiFetchResponse,
} from './http'
import type {
  OpenVpnSocketStatus,
  ActionLogEntry,
  OpenVpnEventProfile,
} from '../types'

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

export async function getOpenVpnEvents() {
  return apiFetch<{ profiles: OpenVpnEventProfile[]; timestamp: string }>('/logs/openvpn-events')
}
