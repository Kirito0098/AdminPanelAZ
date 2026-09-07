import { apiFetch } from './http'

export async function getTrafficOverview(live = true) {
  return apiFetch<import('../types').TrafficOverview>(`/traffic/overview?live=${live}`)
}

export async function getTrafficActiveClients() {
  return apiFetch<{
    active_clients: string[]
    timestamp: string
    node_id: number
    node_name: string
  }>('/traffic/active-clients')
}

export async function getTrafficChart(client: string, range = '7d', protocol = 'all') {
  const params = new URLSearchParams({ client, range, protocol })
  return apiFetch<import('../types').TrafficChartData>(`/traffic/chart?${params}`)
}

export async function getTrafficClientSessions(client: string, limit = 30) {
  const params = new URLSearchParams({ client, limit: String(limit) })
  return apiFetch<import('../types').TrafficClientSessions>(`/traffic/client-sessions?${params}`)
}

export async function resetTraffic(scope: 'all' | 'openvpn' | 'wireguard' | 'amneziawg2' = 'all') {
  return apiFetch('/traffic/reset', { method: 'POST', body: JSON.stringify({ scope }) })
}

export async function getDeletedClientTraffic() {
  return apiFetch<{
    rows: Array<{
      common_name: string
      protocol_type: string
      total_received: number
      total_sent: number
      total_bytes: number
      last_seen_at?: string | null
    }>
    summary: { users_count: number; rows_count: number; total_bytes: number }
  }>('/traffic/deleted-clients')
}

export async function getNeverConnectedClientTraffic() {
  return apiFetch<import('../types').TrafficNeverConnectedResponse>('/traffic/never-connected-clients')
}

export async function deleteDeletedClientTraffic(clientName: string) {
  return apiFetch('/traffic/delete-deleted-client', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName }),
  })
}

export async function cleanupTrafficStatusLogs() {
  return apiFetch<{ message: string }>('/traffic/cleanup-status-logs', { method: 'POST' })
}

export async function getTrafficCleanupSchedule() {
  return apiFetch<{
    period: string
    label: string
    available_periods: Record<string, string>
    openvpn_log_enabled: boolean
  }>('/traffic/cleanup-status-schedule')
}

export async function setTrafficCleanupSchedule(period: string) {
  return apiFetch<{ message: string }>('/traffic/cleanup-status-schedule', {
    method: 'POST',
    body: JSON.stringify({ period }),
  })
}
