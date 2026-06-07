const API_BASE = import.meta.env.VITE_API_URL || '/api'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

function getToken(): string | null {
  return localStorage.getItem('token')
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!response.ok) {
    let detail = 'Ошибка запроса'
    try {
      const data = await response.json()
      detail = data.detail || detail
    } catch {
      detail = await response.text()
    }
    throw new ApiError(typeof detail === 'string' ? detail : JSON.stringify(detail), response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

export async function login(username: string, password: string) {
  return apiFetch<{ access_token: string }>('/auth/login/json', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export async function getMe() {
  return apiFetch<import('../types').User>('/auth/me')
}

export async function changePassword(current: string, newPassword: string) {
  return apiFetch('/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current_password: current, new_password: newPassword }),
  })
}

export async function getConfigs() {
  return apiFetch<import('../types').VpnConfig[]>('/configs')
}

export async function createConfig(data: {
  client_name: string
  vpn_type: import('../types').VpnType
  cert_expire_days?: number
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
  return apiFetch('/configs/sync', { method: 'POST' })
}

export async function getMonitoring() {
  return apiFetch<import('../types').MonitoringOverview>('/monitoring/overview')
}

export async function getSettings() {
  return apiFetch<import('../types').AppSettings>('/settings')
}

export async function updateSettings(data: Partial<import('../types').AppSettings>) {
  return apiFetch<import('../types').AppSettings>('/settings', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function getUsers() {
  return apiFetch<import('../types').User[]>('/users')
}

export async function createUser(data: {
  username: string
  password: string
  role: import('../types').UserRole
}) {
  return apiFetch<import('../types').User>('/users', {
    method: 'POST',
    body: JSON.stringify({ ...data, theme: 'dark', is_active: true }),
  })
}

export async function deleteUser(id: number) {
  return apiFetch(`/users/${id}`, { method: 'DELETE' })
}

export async function updateUser(id: number, data: Record<string, unknown>) {
  return apiFetch<import('../types').User>(`/users/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function downloadProfile(configId: number, path: string) {
  const token = getToken()
  const url = `${API_BASE}/configs/${configId}/download?path=${encodeURIComponent(path)}`
  return fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
}

export async function getNodes() {
  return apiFetch<import('../types').Node[]>('/nodes')
}

export async function getActiveNode() {
  return apiFetch<import('../types').ActiveNode>('/nodes/active')
}

export async function createNode(data: {
  name: string
  host: string
  port: number
  api_key: string
}) {
  return apiFetch<import('../types').Node>('/nodes', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateNode(
  id: number,
  data: Partial<{ name: string; host: string; port: number; api_key: string }>,
) {
  return apiFetch<import('../types').Node>(`/nodes/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function deleteNode(id: number) {
  return apiFetch(`/nodes/${id}`, { method: 'DELETE' })
}

export async function checkNodeHealth(id: number) {
  return apiFetch<{
    node_id: number
    status: import('../types').NodeStatus
    health: Record<string, unknown>
    last_seen_at?: string | null
  }>(`/nodes/${id}/health`, { method: 'POST' })
}

export async function activateNode(id: number) {
  return apiFetch<import('../types').ActiveNode>(`/nodes/${id}/activate`, { method: 'POST' })
}

export async function getDashboardSummary() {
  return apiFetch<import('../types').DashboardSummary>('/monitoring/summary')
}

export async function recreateProfiles() {
  return apiFetch<{ message: string; detail?: string }>('/settings/recreate-profiles', { method: 'POST' })
}

export async function runDoall() {
  return apiFetch<{ message: string; detail?: string }>('/settings/run-doall', { method: 'POST' })
}

export async function restartService(serviceName: string) {
  return apiFetch<{ message: string; detail?: string }>('/settings/restart-service', {
    method: 'POST',
    body: JSON.stringify({ service_name: serviceName }),
  })
}

export async function getBackups() {
  return apiFetch<import('../types').BackupEntry[]>('/backups')
}

export async function createBackup(includeConfigs = false) {
  return apiFetch<import('../types').BackupEntry>('/backups/create', {
    method: 'POST',
    body: JSON.stringify({ include_configs: includeConfigs }),
  })
}

export async function restoreBackup(fileName: string) {
  return apiFetch('/backups/restore', {
    method: 'POST',
    body: JSON.stringify({ file_name: fileName }),
  })
}

export async function deleteBackup(fileName: string) {
  return apiFetch(`/backups/${encodeURIComponent(fileName)}`, { method: 'DELETE' })
}

export async function getBackupSettings() {
  return apiFetch<import('../types').BackupSettings>('/backups/settings')
}

export async function updateBackupSettings(data: Partial<import('../types').BackupSettings>) {
  return apiFetch<import('../types').BackupSettings>('/backups/settings', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function getTelegramSettings() {
  return apiFetch<import('../types').TelegramSettings>('/settings/telegram')
}

export async function updateTelegramSettings(data: {
  bot_token?: string
  chat_id?: string
  notify_enabled?: boolean
  notify_on_backup?: boolean
}) {
  return apiFetch<import('../types').TelegramSettings>('/settings/telegram', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function testTelegram() {
  return apiFetch('/settings/telegram/test', { method: 'POST' })
}

export function getQrUrl(configId: number, path: string) {
  const token = getToken()
  const params = new URLSearchParams({ path })
  return `${API_BASE}/configs/${configId}/qr?${params}${token ? '' : ''}`
}

export async function getRoutingOverview() {
  return apiFetch<import('../types').RoutingOverview>('/routing/overview')
}

export async function toggleRoutingProvider(filename: string, enabled: boolean) {
  return apiFetch(`/routing/providers/${encodeURIComponent(filename)}/enabled`, {
    method: 'POST',
    body: JSON.stringify({ enabled }),
  })
}

export async function applyRoutingPreset(presetKey: string) {
  return apiFetch(`/routing/presets/${encodeURIComponent(presetKey)}/apply`, { method: 'POST' })
}

export async function syncRoutingProviders() {
  return apiFetch('/routing/sync', { method: 'POST' })
}

export async function applyRouting() {
  return apiFetch<{ message: string; detail?: unknown }>('/routing/apply', { method: 'POST' })
}

export async function getCidrDbStatus() {
  return apiFetch<import('../types').CidrDbStatus>('/routing/cidr-db/status')
}

export async function getAntifilterStatus() {
  return apiFetch<import('../types').AntifilterStatus>('/routing/cidr-db/antifilter/status')
}

export async function refreshCidrDb(selectedFiles?: string[]) {
  return apiFetch<{ success: boolean; task_id: string; message: string }>('/routing/cidr-db/refresh', {
    method: 'POST',
    body: JSON.stringify({ selected_files: selectedFiles ?? null }),
  })
}

export async function refreshAntifilter() {
  return apiFetch<{ success: boolean; task_id: string; message: string }>('/routing/cidr-db/antifilter/refresh', {
    method: 'POST',
  })
}

export async function generateCidrFromDb(options?: {
  filter_by_antifilter?: boolean
  exclude_ru_cidrs?: boolean
  apply_after?: boolean
}) {
  return apiFetch<{ success: boolean; task_id: string; message: string }>('/routing/cidr-db/generate', {
    method: 'POST',
    body: JSON.stringify({
      action: 'generate',
      filter_by_antifilter: options?.filter_by_antifilter ?? false,
      exclude_ru_cidrs: options?.exclude_ru_cidrs ?? false,
      apply_after: options?.apply_after ?? false,
      sync_after: true,
    }),
  })
}

export async function getCidrPipelineTask(taskId: string) {
  return apiFetch<{ success: boolean; task: import('../types').CidrPipelineTask }>(
    `/routing/cidr-db/tasks/${encodeURIComponent(taskId)}`,
  )
}

export async function getTrafficOverview() {
  return apiFetch<import('../types').TrafficOverview>('/traffic/overview')
}

export async function getTrafficChart(client: string, range = '7d', protocol = 'all') {
  const params = new URLSearchParams({ client, range, protocol })
  return apiFetch<import('../types').TrafficChartData>(`/traffic/chart?${params}`)
}

export async function resetTraffic(scope: 'all' | 'openvpn' | 'wireguard' = 'all') {
  return apiFetch('/traffic/reset', { method: 'POST', body: JSON.stringify({ scope }) })
}

export async function createOneTimeLink(configId: number, path: string) {
  const params = new URLSearchParams({ path })
  return apiFetch<import('../types').OneTimeLinkResponse>(
    `/configs/${configId}/one-time-link?${params}`,
    { method: 'POST' },
  )
}

export async function getEditFiles() {
  return apiFetch<import('../types').EditFileEntry[]>('/edit-files')
}

export async function getEditFileContent(key: string) {
  return apiFetch<{ key: string; content: string }>(`/edit-files/${key}`)
}

export async function saveEditFile(key: string, content: string) {
  return apiFetch(`/edit-files/${key}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  })
}

export async function getClientPolicies(clients: string) {
  const params = new URLSearchParams({ clients })
  return apiFetch<Record<string, { openvpn: import('../types').ClientAccessPolicy; wireguard: import('../types').ClientAccessPolicy }>>(
    `/client-access/policies?${params}`,
  )
}

export async function openvpnTempBlock(clientName: string, days: number) {
  return apiFetch('/client-access/openvpn/temp-block', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName, days }),
  })
}

export async function openvpnUnblock(clientName: string) {
  return apiFetch('/client-access/openvpn/unblock', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName }),
  })
}

export async function openvpnPermanentBlock(clientName: string) {
  return apiFetch('/client-access/openvpn/permanent-block', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName }),
  })
}

export async function wgSetExpiry(clientName: string, days: number, extend = false) {
  return apiFetch('/client-access/wireguard/set-expiry', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName, days, extend }),
  })
}

export async function wgTempBlock(clientName: string, days: number) {
  return apiFetch('/client-access/wireguard/temp-block', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName, days }),
  })
}

export async function wgUnblock(clientName: string) {
  return apiFetch('/client-access/wireguard/unblock', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName }),
  })
}

export async function wgPermanentBlock(clientName: string) {
  return apiFetch('/client-access/wireguard/permanent-block', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName }),
  })
}

export async function getGameFilters() {
  return apiFetch<{ games: import('../types').GameFilterItem[] }>('/routing/game-filters')
}

export async function syncGameFilters(modes: Record<string, string>, runDoall = true) {
  return apiFetch('/routing/game-filters/sync', {
    method: 'POST',
    body: JSON.stringify({ modes, include_domains: true, run_doall: runDoall }),
  })
}

export async function getSecuritySettings() {
  return apiFetch<import('../types').SecuritySettings>('/security')
}

export async function updateSecuritySettings(data: Partial<import('../types').SecuritySettings & { qr_download_pin?: string }>) {
  return apiFetch<import('../types').SecuritySettings>('/security', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function getServerMetrics(accurate = false) {
  return apiFetch<import('../types').ServerMetrics>(`/server-monitor/metrics?accurate=${accurate}`)
}

export async function getActionLogs(limit = 100) {
  return apiFetch<import('../types').ActionLogEntry[]>(`/logs/actions?limit=${limit}`)
}

export async function getConnectionLogs() {
  return apiFetch<{ openvpn_clients: unknown[]; wireguard_peers: unknown[]; timestamp: string }>('/logs/connections')
}

export async function checkSystemUpdates() {
  return apiFetch<{ updates_available: boolean; commits_behind: number; local_hash?: string }>('/system/updates')
}

export function downloadBackup(fileName: string) {
  const token = getToken()
  const url = `${API_BASE}/backups/${encodeURIComponent(fileName)}/download`
  return fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
}

export async function fetchQrBlob(configId: number, path: string) {
  const token = getToken()
  const params = new URLSearchParams({ path })
  const response = await fetch(`${API_BASE}/configs/${configId}/qr?${params}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) throw new ApiError('Ошибка генерации QR', response.status)
  return response.blob()
}
