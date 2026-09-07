import {
  API_BASE,
  apiFetch,
  getToken,
} from './http'

export async function getMonitoring(
  scope: 'node' | 'all' = 'node',
  haMode: 'dedupe' | 'raw' = 'dedupe',
) {
  const params = new URLSearchParams({ scope, ha_mode: haMode })
  return apiFetch<import('../types').MonitoringOverview>(`/monitoring/overview?${params}`)
}

export async function getNocIncidents(limit = 20) {
  return apiFetch<import('../types').NocIncidentsResponse>(`/monitoring/incidents?limit=${limit}`)
}

export async function getConnectionHistory(
  period: '1h' | '6h' | '24h' = '1h',
  scope: 'node' | 'all' = 'node',
) {
  const params = new URLSearchParams({ period, scope })
  return apiFetch<import('../types').ConnectionHistoryResponse>(
    `/monitoring/connection-history?${params}`,
  )
}

export async function getGeoRoutingHint(clientIp?: string) {
  const query = clientIp ? `?client_ip=${encodeURIComponent(clientIp)}` : ''
  return apiFetch<import('../types').GeoRoutingHint>(`/nodes/geo-routing-hint${query}`)
}

export function openMonitoringStream(
  onData: (data: import('../types').MonitoringOverview) => void,
  onError?: (message: string) => void,
  scope: 'node' | 'all' = 'node',
  haMode: 'dedupe' | 'raw' = 'dedupe',
): EventSource | null {
  const token = getToken()
  if (!token) return null
  const params = new URLSearchParams({
    token,
    scope,
    ha_mode: haMode,
  })
  const url = `${API_BASE}/monitoring/stream?${params}`
  const source = new EventSource(url)
  source.onmessage = (event) => {
    try {
      onData(JSON.parse(event.data) as import('../types').MonitoringOverview)
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
  return source
}

export async function getResourceHistory(period: '1d' | '7d' | '30d' = '1d') {
  return apiFetch<import('../types').ResourceHistory>(`/monitoring/resource-history?period=${period}`)
}

export async function getPanelResourceHistory(period: '1d' | '7d' | '30d' = '1d') {
  return apiFetch<import('../types').PanelResourceHistory>(
    `/monitoring/panel-resource-history?period=${period}`,
  )
}

export async function getPanelResourceCurrent() {
  return apiFetch<import('../types').PanelResourceCurrent>('/monitoring/panel-resource-current')
}

export async function getDashboardSummary() {
  return apiFetch<import('../types').DashboardSummary>('/monitoring/summary')
}
