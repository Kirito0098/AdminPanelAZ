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

let refreshPromise: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    })
      .then(async (response) => {
        if (!response.ok) return null
        const data = await response.json()
        const token = data.access_token as string
        localStorage.setItem('token', token)
        return token
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

export async function apiFetch<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: 'include' })
  if (response.status === 401 && retry && !path.startsWith('/auth/')) {
    const newToken = await refreshAccessToken()
    if (newToken) {
      return apiFetch<T>(path, options, false)
    }
    localStorage.removeItem('token')
  }
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

export type LoginResult =
  | { access_token: string; requires_2fa?: false }
  | { requires_2fa: true; temp_token: string }

export async function login(username: string, password: string): Promise<LoginResult> {
  return apiFetch<LoginResult>('/auth/login/json', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export async function loginWithCaptcha(
  username: string,
  password: string,
  captchaId: string,
  captchaText: string,
): Promise<LoginResult> {
  return apiFetch<LoginResult>('/auth/login/json', {
    method: 'POST',
    body: JSON.stringify({ username, password, captcha_id: captchaId, captcha_text: captchaText }),
  })
}

export async function login2FA(tempToken: string, code: string) {
  return apiFetch<{ access_token: string }>('/auth/login/2fa', {
    method: 'POST',
    body: JSON.stringify({ temp_token: tempToken, code }),
  })
}

export async function logoutApi() {
  return apiFetch('/auth/logout', { method: 'POST' })
}

export async function get2FAStatus() {
  return apiFetch<{ enabled: boolean; backup_codes_remaining: number }>('/auth/2fa/status')
}

export async function setup2FA() {
  return apiFetch<{ secret: string; otpauth_uri: string; qr_data_url: string }>('/auth/2fa/setup', {
    method: 'POST',
  })
}

export async function enable2FA(code: string) {
  return apiFetch<{ backup_codes: string[] }>('/auth/2fa/enable', {
    method: 'POST',
    body: JSON.stringify({ code }),
  })
}

export async function disable2FA(code: string) {
  return apiFetch('/auth/2fa/disable', {
    method: 'POST',
    body: JSON.stringify({ code }),
  })
}

export async function regenerate2FABackupCodes(code: string) {
  return apiFetch<{ backup_codes: string[] }>('/auth/2fa/regenerate-backup-codes', {
    method: 'POST',
    body: JSON.stringify({ code }),
  })
}

export async function rotateNodeApiKey(nodeId: number) {
  return apiFetch<{ message: string; node_id: number }>(`/nodes/${nodeId}/rotate-key`, {
    method: 'POST',
  })
}

export async function getCaptchaRequired() {
  return apiFetch<{ required: boolean }>('/auth/captcha/required')
}

export async function getTelegramLoginConfig() {
  return apiFetch<{ enabled: boolean; bot_username: string }>('/auth/telegram/config')
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

export async function getViewerAccess(userId: number) {
  return apiFetch<{ user_id: number; config_groups: string[] }>(`/system/viewer-access/${userId}`)
}

export async function setViewerAccess(userId: number, configGroups: string[]) {
  return apiFetch<{ message: string }>('/system/viewer-access', {
    method: 'PUT',
    body: JSON.stringify({ user_id: userId, config_groups: configGroups }),
  })
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

export async function checkNodeUpdates(id: number) {
  return apiFetch<{
    node_id: number
    agent: Record<string, unknown>
    antizapret: Record<string, unknown>
  }>(`/nodes/${id}/updates`)
}

export async function applyNodeUpdate(
  id: number,
  data: { scope?: 'all' | 'agent' | 'antizapret'; run_doall?: boolean } = {},
) {
  return apiFetch<{
    node_id: number
    success: boolean
    message: string
    restarting: boolean
    before: Record<string, unknown>
    after: Record<string, unknown>
    detail: Record<string, unknown>
    errors: string[]
  }>(`/nodes/${id}/update`, {
    method: 'POST',
    body: JSON.stringify({ scope: data.scope ?? 'all', run_doall: data.run_doall ?? true }),
  })
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

export async function getAdminNotifySettings() {
  return apiFetch<import('../types').AdminNotifySettings>('/settings/admin-notify')
}

export async function updateAdminNotifySettings(data: {
  telegram_id?: string
  events?: Record<string, boolean>
}) {
  return apiFetch<import('../types').AdminNotifySettings>('/settings/admin-notify', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function testAdminNotify() {
  return apiFetch('/settings/admin-notify/test', { method: 'POST' })
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

export async function saveEditFilesBatch(files: Record<string, string>, runDoall = false) {
  return apiFetch<{ message: string; detail?: string }>('/edit-files/batch', {
    method: 'POST',
    body: JSON.stringify({ files, run_doall: runDoall }),
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

export async function openvpnSetTrafficLimit(
  clientName: string,
  limitValue: number,
  limitUnit = 'MB',
  limitPeriodDays?: number | null,
) {
  return apiFetch('/client-access/openvpn/set-traffic-limit', {
    method: 'POST',
    body: JSON.stringify({
      client_name: clientName,
      limit_value: limitValue,
      limit_unit: limitUnit,
      limit_period_days: limitPeriodDays ?? null,
    }),
  })
}

export async function openvpnClearTrafficLimit(clientName: string) {
  return apiFetch('/client-access/openvpn/clear-traffic-limit', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName }),
  })
}

export async function wgSetTrafficLimit(
  clientName: string,
  limitValue: number,
  limitUnit = 'MB',
  limitPeriodDays?: number | null,
) {
  return apiFetch('/client-access/wireguard/set-traffic-limit', {
    method: 'POST',
    body: JSON.stringify({
      client_name: clientName,
      limit_value: limitValue,
      limit_unit: limitUnit,
      limit_period_days: limitPeriodDays ?? null,
    }),
  })
}

export async function wgClearTrafficLimit(clientName: string) {
  return apiFetch('/client-access/wireguard/clear-traffic-limit', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName }),
  })
}

export async function getFeatureModules() {
  return apiFetch<import('../types').FeatureModulesResponse>('/feature-modules')
}

export async function getFeatureToggles() {
  return apiFetch<import('../types').FeatureTogglesResponse>('/feature-toggles')
}

export async function updateFeatureToggles(toggles: Record<string, boolean>) {
  return apiFetch<import('../types').FeatureTogglesResponse>('/feature-toggles', {
    method: 'PUT',
    body: JSON.stringify({ toggles }),
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

export async function getAntizapretSettings() {
  return apiFetch<import('../types').AntizapretSettingsResponse>('/routing/antizapret-settings')
}

export async function updateAntizapretSettings(updates: Record<string, string | boolean>) {
  return apiFetch<import('../types').AntizapretSettingsUpdateResponse>('/routing/antizapret-settings', {
    method: 'PUT',
    body: JSON.stringify(updates),
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

export async function getServerInterfaces() {
  return apiFetch<{ interfaces: string[]; groups?: Record<string, string[]> }>('/server-monitor/interfaces')
}

export async function getBandwidthChart(iface: string, range: string) {
  return apiFetch<import('../types').BandwidthChart>(
    `/server-monitor/bandwidth?iface=${encodeURIComponent(iface)}&range_key=${range}`,
  )
}

export async function openvpnDisconnect(clientName: string) {
  return apiFetch('/client-access/openvpn/disconnect', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName }),
  })
}

export async function collectTests() {
  return apiFetch<{ tests: Array<{ id: string; title: string; description?: string }>; count: number }>(
    '/tests/collect',
  )
}

export async function runTests(testIds: string[] = []) {
  return apiFetch<{ task_id: string; message: string }>('/tests/run', {
    method: 'POST',
    body: JSON.stringify({ test_ids: testIds }),
  })
}

export async function getTestTask(taskId: string) {
  return apiFetch<import('../types').CidrPipelineTask>(`/tests/tasks/${taskId}`)
}

export async function applySystemUpdate() {
  return apiFetch<{ message: string }>('/system/update', { method: 'POST' })
}

export async function getScannerBans() {
  return apiFetch<{ active_bans: import('../types').ScannerBan[] }>('/security/scanner-bans')
}

export async function unbanScannerIp(ip: string) {
  return apiFetch('/security/scanner-bans/unban', {
    method: 'POST',
    body: JSON.stringify({ ip }),
  })
}

export async function getActionLogs(limit = 100) {
  return apiFetch<import('../types').ActionLogEntry[]>(`/logs/actions?limit=${limit}`)
}

export async function getConnectionLogs() {
  return apiFetch<import('../types').ConnectionLogsSnapshot>('/logs/connections')
}

export async function getOpenVpnEvents() {
  return apiFetch<{ profiles: import('../types').OpenVpnEventProfile[]; timestamp: string }>('/logs/openvpn-events')
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
