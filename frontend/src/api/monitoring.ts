import { apiFetch } from './http'
import { openTicketEventSource, type StreamHandle } from './streamTicket'
import type {
  MonitoringOverview,
  NocIncidentsResponse,
  ConnectionHistoryResponse,
  GeoRoutingHint,
  ResourceHistory,
  PanelResourceHistory,
  PanelResourceCurrent,
} from '../types'

export async function getMonitoring(
  scope: 'node' | 'all' = 'node',
  haMode: 'dedupe' | 'raw' = 'dedupe',
) {
  const params = new URLSearchParams({ scope, ha_mode: haMode })
  return apiFetch<MonitoringOverview>(`/monitoring/overview?${params}`)
}

export async function getNocIncidents(limit = 20) {
  return apiFetch<NocIncidentsResponse>(`/monitoring/incidents?limit=${limit}`)
}

export async function getConnectionHistory(
  period: '1h' | '6h' | '24h' = '1h',
  scope: 'node' | 'all' = 'node',
) {
  const params = new URLSearchParams({ period, scope })
  return apiFetch<ConnectionHistoryResponse>(
    `/monitoring/connection-history?${params}`,
  )
}

export async function getGeoRoutingHint(clientIp?: string) {
  const query = clientIp ? `?client_ip=${encodeURIComponent(clientIp)}` : ''
  return apiFetch<GeoRoutingHint>(`/nodes/geo-routing-hint${query}`)
}

const MONITORING_RECONNECT_MS = 3000

export function openMonitoringStream(
  onData: (data: MonitoringOverview) => void,
  onError?: (message: string) => void,
  scope: 'node' | 'all' = 'node',
  haMode: 'dedupe' | 'raw' = 'dedupe',
): StreamHandle {
  return openTicketEventSource({
    stream: 'monitoring',
    path: '/monitoring/stream',
    params: { scope, ha_mode: haMode },
    reconnectDelayMs: MONITORING_RECONNECT_MS,
    onError,
    attach: (source) => {
      source.onmessage = (event) => {
        try {
          onData(JSON.parse(event.data) as MonitoringOverview)
        } catch {
          onError?.('Ошибка разбора потока мониторинга')
        }
      }
      source.addEventListener('error', (event) => {
        if (event instanceof MessageEvent && event.data) {
          try {
            const payload = JSON.parse(event.data) as { detail?: string }
            onError?.(payload.detail || 'Ошибка потока мониторинга')
          } catch {
            onError?.('Ошибка потока мониторинга')
          }
        }
      })
    },
  })
}

export async function getResourceHistory(period: '1d' | '7d' | '30d' = '1d') {
  return apiFetch<ResourceHistory>(`/monitoring/resource-history?period=${period}`)
}

export async function getPanelResourceHistory(period: '1d' | '7d' | '30d' = '1d') {
  return apiFetch<PanelResourceHistory>(
    `/monitoring/panel-resource-history?period=${period}`,
  )
}

export async function getPanelResourceCurrent() {
  return apiFetch<PanelResourceCurrent>('/monitoring/panel-resource-current')
}
