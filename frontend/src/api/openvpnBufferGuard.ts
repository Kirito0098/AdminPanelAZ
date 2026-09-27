import { apiFetch } from './http'
import type {
  OpenVpnBufferGuardEvent,
  OpenVpnBufferGuardSettings,
} from '@/types'

export type OpenVpnBufferGuardSettingsPayload = OpenVpnBufferGuardSettings

export async function getBufferGuardSettings(
  nodeId: number,
): Promise<OpenVpnBufferGuardSettings> {
  return apiFetch<OpenVpnBufferGuardSettings>(
    `/openvpn-buffer-guard/settings?node_id=${encodeURIComponent(String(nodeId))}`,
  )
}

export async function putBufferGuardSettings(
  payload: OpenVpnBufferGuardSettingsPayload,
): Promise<OpenVpnBufferGuardSettings> {
  return apiFetch<OpenVpnBufferGuardSettings>('/openvpn-buffer-guard/settings', {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export async function getBufferGuardEvents(
  nodeId: number,
  limit = 20,
): Promise<OpenVpnBufferGuardEvent[]> {
  const params = new URLSearchParams({
    node_id: String(nodeId),
    limit: String(limit),
  })
  return apiFetch<OpenVpnBufferGuardEvent[]>(
    `/openvpn-buffer-guard/events?${params.toString()}`,
  )
}

export interface OpenVpnBufferGuardScanResult {
  unit: string
  total: number
  threshold: number
  threshold_exceeded: boolean
  mode: string
  top_cn?: string | null
  top_real_address?: string | null
  manual: boolean
  actions: unknown[]
  result: string
}

export async function scanBufferGuard(
  nodeId: number,
): Promise<OpenVpnBufferGuardScanResult[]> {
  return apiFetch<OpenVpnBufferGuardScanResult[]>('/openvpn-buffer-guard/scan', {
    method: 'POST',
    body: JSON.stringify({ node_id: nodeId }),
  })
}

