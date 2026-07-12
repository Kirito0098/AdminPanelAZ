import { apiBase as API_BASE } from '@/lib/panelBase'
import { parseHttpErrorBody } from '@/lib/httpErrorMessage'

export class ApiError extends Error {
  status: number
  payload?: unknown
  constructor(message: string, status: number, payload?: unknown) {
    super(message)
    this.status = status
    this.payload = payload
  }
}

import { getActiveTimeZone } from '@/lib/datetime'
import { clearWebSessionId, getWebSessionId } from '@/lib/webSession'

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
  return apiFetchAtBase<T>(API_BASE, path, options, retry)
}

export async function apiFetchAtBase<T>(
  base: string,
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<T> {
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const sessionId = getWebSessionId()
  if (sessionId) headers.set('X-Web-Session-Id', sessionId)
  if (!headers.has('X-Client-Timezone')) {
    const tz = getActiveTimeZone()
    if (tz) headers.set('X-Client-Timezone', tz)
  }

  const normalizedBase = base.endsWith('/') ? base.slice(0, -1) : base
  let response: Response
  try {
    response = await fetch(`${normalizedBase}${path}`, { ...options, headers, credentials: 'include' })
  } catch {
    throw new ApiError(
      'Не удалось связаться с сервером. Возможен перезапуск панели — подождите и откройте новый адрес.',
      0,
    )
  }
  if (response.status === 401 && retry && !path.startsWith('/auth/') && normalizedBase === API_BASE) {
    const newToken = await refreshAccessToken()
    if (newToken) {
      return apiFetchAtBase<T>(base, path, options, false)
    }
    localStorage.removeItem('token')
  }
  if (!response.ok) {
    const body = await response.text()
    let payload: unknown
    if (body) {
      try {
        payload = JSON.parse(body)
      } catch {
        payload = undefined
      }
    }
    const detail = parseHttpErrorBody(body, response.status)
    throw new ApiError(detail, response.status, payload)
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

export type LoginResult =
  | { access_token: string; web_session_id?: string; requires_2fa?: false }
  | { requires_2fa: true; temp_token: string; passkey_available?: boolean }

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
  return apiFetch<{ access_token: string; web_session_id?: string }>('/auth/login/2fa', {
    method: 'POST',
    body: JSON.stringify({ temp_token: tempToken, code }),
  })
}

export async function logoutApi() {
  try {
    return await apiFetch('/auth/logout', { method: 'POST' })
  } finally {
    clearWebSessionId()
  }
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

export type PasskeyCredential = {
  id: number
  nickname: string
  created_at: string
  last_used_at: string | null
}

export async function getPasskeys() {
  return apiFetch<{ credentials: PasskeyCredential[]; count: number }>('/auth/passkeys')
}

export async function getPasskeyRegisterOptions() {
  return apiFetch<{ options: Record<string, unknown> & { sessionKey?: string } }>(
    '/auth/passkeys/register/options',
    { method: 'POST' },
  )
}

export async function verifyPasskeyRegister(
  sessionKey: string,
  credential: unknown,
  nickname?: string,
) {
  return apiFetch<PasskeyCredential>('/auth/passkeys/register/verify', {
    method: 'POST',
    body: JSON.stringify({ session_key: sessionKey, credential, nickname }),
  })
}

export async function deletePasskey(credentialId: number) {
  return apiFetch('/auth/passkeys/' + credentialId, { method: 'DELETE' })
}

export async function renamePasskey(credentialId: number, nickname: string) {
  return apiFetch<PasskeyCredential>('/auth/passkeys/' + credentialId, {
    method: 'PATCH',
    body: JSON.stringify({ nickname }),
  })
}

export async function getPasskeyLoginOptions(tempToken: string) {
  return apiFetch<{ options: Record<string, unknown> & { sessionKey?: string } }>(
    '/auth/login/passkey/options',
    {
      method: 'POST',
      body: JSON.stringify({ temp_token: tempToken }),
    },
  )
}

export async function verifyPasskeyLogin(tempToken: string, sessionKey: string, credential: unknown) {
  return apiFetch<{ access_token: string; web_session_id?: string }>('/auth/login/passkey/verify', {
    method: 'POST',
    body: JSON.stringify({ temp_token: tempToken, session_key: sessionKey, credential }),
  })
}

export async function rotateNodeApiKey(nodeId: number) {
  return apiFetch<{ message: string; node_id: number }>(`/nodes/${nodeId}/rotate-key`, {
    method: 'POST',
  })
}

export async function disableNodeMtls(nodeId: number) {
  return apiFetch<import('../types').NodeMtlsDisableResult>(`/nodes/${nodeId}/disable-mtls`, {
    method: 'POST',
  })
}

export async function enableNodeMtls(nodeId: number) {
  return apiFetch<{ message: string; node_id: number; mtls_enabled: boolean }>(
    `/nodes/${nodeId}/enable-mtls`,
    { method: 'POST' },
  )
}

export async function getNodeMtlsStatus() {
  return apiFetch<import('../types').NodeMtlsStatus>('/nodes/mtls/status')
}

export async function getCaptchaRequired() {
  return apiFetch<{ required: boolean }>('/auth/captcha/required')
}

export async function getTelegramLoginConfig() {
  return apiFetch<{
    enabled: boolean
    auth_method?: 'oidc' | 'legacy' | 'none'
    bot_username: string
    max_age_seconds?: number
    oidc_enabled?: boolean
    oidc_client_id?: string
    legacy_enabled?: boolean
    oidc_start_url?: string
  }>('/auth/telegram/config')
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

export async function getActiveWebSessions() {
  return apiFetch<import('../types').ActiveWebSession[]>('/security/active-sessions')
}

export async function revokeActiveWebSession(sessionId: string) {
  return apiFetch(`/security/active-sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  })
}

export async function getMonitoring(scope: 'node' | 'all' = 'node') {
  return apiFetch<import('../types').MonitoringOverview>(`/monitoring/overview?scope=${scope}`)
}

export async function getGlobalDashboardSummary() {
  return apiFetch<import('../types').GlobalDashboardSummary>('/monitoring/global-summary')
}

export async function getNodesCompare() {
  return apiFetch<import('../types').GlobalDashboardSummary>('/monitoring/nodes-compare')
}

export async function getGeoRoutingHint(clientIp?: string) {
  const query = clientIp ? `?client_ip=${encodeURIComponent(clientIp)}` : ''
  return apiFetch<import('../types').GeoRoutingHint>(`/nodes/geo-routing-hint${query}`)
}

export async function getNodePolicySummary() {
  return apiFetch<import('../types').NodePolicySummary[]>('/client-access/policy-summary-by-node')
}

export async function getNodeDefaultPolicy(nodeId: number) {
  return apiFetch<import('../types').NodeDefaultPolicy>(`/client-access/node-defaults/${nodeId}`)
}

export async function updateNodeDefaultPolicy(
  nodeId: number,
  payload: import('../types').NodeDefaultPolicyUpdate,
) {
  return apiFetch<import('../types').NodeDefaultPolicy>(`/client-access/node-defaults/${nodeId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function openMonitoringStream(
  onData: (data: import('../types').MonitoringOverview) => void,
  onError?: (message: string) => void,
): EventSource | null {
  const token = getToken()
  if (!token) return null
  const url = `${API_BASE}/monitoring/stream?token=${encodeURIComponent(token)}`
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
  }>(`/nodes/${id}/updates`)
}

export async function applyNodeUpdate(id: number) {
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
    body: JSON.stringify({}),
  })
}

export async function restartNodeAgent(id: number) {
  return apiFetch<{
    node_id: number
    success: boolean
    message: string
    restarting: boolean
  }>(`/nodes/${id}/restart-agent`, {
    method: 'POST',
  })
}

export async function rollingNodeUpdate(nodeIds: number[]) {
  return apiFetch<import('../types').BackgroundTaskAccepted>('/nodes/update-roll', {
    method: 'POST',
    body: JSON.stringify({ node_ids: nodeIds }),
  })
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

export async function getEventWebhookSettings() {
  return apiFetch<import('../types').EventWebhookSettings>('/security/event-webhooks')
}

export async function updateEventWebhookSettings(data: {
  url?: string
  secret?: string
  enabled?: boolean
  events?: Array<{ key: string; enabled: boolean }>
}) {
  return apiFetch<import('../types').EventWebhookSettings>('/security/event-webhooks', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function getAuditStreamSettings() {
  return apiFetch<import('../types').AuditStreamSettings>('/security/audit-stream')
}

export async function updateAuditStreamSettings(data: {
  enabled?: boolean
  mode?: 'http' | 'syslog' | 'both'
  http_url?: string
  secret?: string
  syslog_host?: string
  syslog_port?: number
  syslog_protocol?: 'udp' | 'tcp'
  format?: 'json' | 'cef'
}) {
  return apiFetch<import('../types').AuditStreamSettings>('/security/audit-stream', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function testAuditStream() {
  return apiFetch<{ results: Record<string, string> }>('/security/audit-stream/test', {
    method: 'POST',
  })
}

export async function getNodeSyncGroups() {
  return apiFetch<import('../types').NodeSyncGroup[]>('/nodes/sync-groups')
}

export async function createNodeSyncGroup(data: {
  name: string
  shared_domain: string
  primary_node_id: number
  replica_node_ids: number[]
  sync_mode?: string
}) {
  return apiFetch<import('../types').NodeSyncGroup>('/nodes/sync-groups', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateNodeSyncGroup(
  id: number,
  data: Partial<{
    name: string
    shared_domain: string
    primary_node_id: number
    replica_node_ids: number[]
    sync_mode: string
  }>,
) {
  return apiFetch<import('../types').NodeSyncGroup>(`/nodes/sync-groups/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function deleteNodeSyncGroup(id: number) {
  return apiFetch<{ message: string }>(`/nodes/sync-groups/${id}`, { method: 'DELETE' })
}

export async function getNodeSyncGroupStatus(id: number) {
  return apiFetch<import('../types').NodeSyncGroupStatus>(`/nodes/sync-groups/${id}/status`)
}

export async function pushNodeSyncGroupFull(id: number) {
  return apiFetch<{
    task_id: string
    group_id: number
    message: string
    queued?: boolean
    status_url?: string | null
  }>(`/nodes/sync-groups/${id}/push-full`, { method: 'POST' })
}

export async function setupNodeSyncGroup(id: number) {
  return apiFetch<{
    task_id: string
    group_id: number
    message: string
    queued?: boolean
    status_url?: string | null
  }>(`/nodes/sync-groups/${id}/setup`, { method: 'POST' })
}

export async function applyNodeSyncGroupSharedDomain(id: number) {
  return apiFetch<{
    task_id: string
    group_id: number
    message: string
    queued?: boolean
    status_url?: string | null
  }>(`/nodes/sync-groups/${id}/apply-shared-domain`, { method: 'POST' })
}

export async function verifyNodeSyncGroup(id: number) {
  return apiFetch<import('../types').NodeSyncVerifyResult>(`/nodes/sync-groups/${id}/verify`, {
    method: 'POST',
  })
}

export async function getDashboardSummary() {
  return apiFetch<import('../types').DashboardSummary>('/monitoring/summary')
}

export async function recreateProfiles() {
  return apiFetch<{ message: string; detail?: string }>('/settings/recreate-profiles', { method: 'POST' })
}

export async function runDoall() {
  return apiFetch<import('../types').BackgroundTaskAcceptedResponse>('/settings/run-doall', { method: 'POST' })
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

export async function createBackup(
  includeConfigs = false,
  includeAntizapretBackup = false,
  sendToTelegram = false,
) {
  return apiFetch<import('../types').BackupEntry>('/backups/create', {
    method: 'POST',
    body: JSON.stringify({
      include_configs: includeConfigs,
      include_antizapret_backup: includeAntizapretBackup,
      send_to_telegram: sendToTelegram,
    }),
  })
}

export async function restoreBackup(fileName: string) {
  return apiFetch<{ message: string; detail?: Record<string, unknown> }>('/backups/restore', {
    method: 'POST',
    body: JSON.stringify({ file_name: fileName }),
  })
}

export async function uploadBackup(file: File, restore = false) {
  const form = new FormData()
  form.append('file', file)
  form.append('restore', restore ? 'true' : 'false')
  return apiFetch<import('../types').BackupEntry>('/backups/upload', {
    method: 'POST',
    body: form,
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

export async function getVpnNetworkSettings() {
  return apiFetch<import('../types').VpnNetworkSettings>('/settings/vpn-network')
}

export async function getVpnNetworkDomainSsl(domain: string) {
  const params = new URLSearchParams({ domain })
  return apiFetch<import('../types').VpnNetworkDomainSslStatus>(
    `/settings/vpn-network/domain-ssl?${params.toString()}`,
  )
}

export async function getVpnNetworkPortStatus(port: number, role: import('../types').VpnNetworkPortRole = 'backend') {
  const params = new URLSearchParams({ port: String(port), role })
  return apiFetch<import('../types').VpnNetworkPortStatus>(
    `/settings/vpn-network/port-status?${params.toString()}`,
  )
}

export async function publishVpnNetwork(data: import('../types').VpnNetworkPublishPayload) {
  return apiFetch<import('../types').BackgroundTaskAcceptedResponse>('/settings/vpn-network/publish', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getTelegramSettings() {
  return apiFetch<import('../types').TelegramSettings>('/settings/telegram')
}

export async function updateTelegramSettings(data: {
  bot_token?: string
  bot_username?: string
  auth_max_age_seconds?: number
  chat_id?: string
  chat_ids?: string[]
  notify_enabled?: boolean
  notify_on_backup?: boolean
  interactive_enabled?: boolean
  auth_method?: 'oidc' | 'legacy'
  oidc_enabled?: boolean
  oidc_client_id?: string
  oidc_client_secret?: string
  legacy_login_enabled?: boolean
}) {
  return apiFetch<import('../types').TelegramSettings>('/settings/telegram', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function registerTelegramWebhook() {
  return apiFetch<import('../types').TelegramSettings>('/settings/telegram/webhook/register', {
    method: 'POST',
  })
}

export async function deleteTelegramWebhook() {
  return apiFetch<import('../types').TelegramSettings>('/settings/telegram/webhook', {
    method: 'DELETE',
  })
}

export async function getTelegramLinkCode() {
  return apiFetch<import('../types').TelegramLinkCode>('/telegram/link-code')
}

export async function getTelegramBotInfo() {
  return apiFetch<import('../types').TelegramBotInfo>('/telegram/bot-info')
}

export async function testTelegram() {
  return apiFetch('/settings/telegram/test', { method: 'POST' })
}

export async function getAdminNotifySettings() {
  return apiFetch<import('../types').AdminNotifySettings>('/settings/admin-notify')
}

export async function updateAdminNotifySettings(data: {
  telegram_id?: string
  recipient_user_ids?: number[]
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

export async function testAdminNotifyEvent(event: string) {
  return apiFetch<{ message: string }>('/settings/admin-notify/test-event', {
    method: 'POST',
    body: JSON.stringify({ event }),
  })
}

export async function testNocReportPreview(period: 'daily' | 'weekly' = 'daily') {
  return apiFetch<{ message: string }>('/settings/admin-notify/test-noc-report', {
    method: 'POST',
    body: JSON.stringify({ period }),
  })
}

export async function testNocWeeklyImagePreview() {
  return apiFetch<{ message: string }>('/settings/admin-notify/test-noc-image', {
    method: 'POST',
  })
}

/** @deprecated use testNocWeeklyImagePreview */
export async function testNocWeeklyPdfPreview() {
  return testNocWeeklyImagePreview()
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

export async function getRoutingProviderContent(filename: string) {
  return apiFetch<import('../types').RoutingProviderContent>(
    `/routing/providers/${encodeURIComponent(filename)}`,
  )
}

export async function saveRoutingProviderContent(filename: string, content: string) {
  return apiFetch<{ filename: string; cidr_count: number }>(
    `/routing/providers/${encodeURIComponent(filename)}`,
    { method: 'PUT', body: JSON.stringify({ content }) },
  )
}

export async function getRoutingResults() {
  return apiFetch<{ files: import('../types').RouteResultFileEntry[] }>('/routing/results')
}

export async function getRoutingResultContent(key: string) {
  return apiFetch<{ key: string; filename: string; content: string; line_count: number }>(
    `/routing/results/${encodeURIComponent(key)}`,
  )
}

export async function syncRoutingProviders() {
  return apiFetch('/routing/sync', { method: 'POST' })
}

export async function applyRouting() {
  return apiFetch<import('../types').BackgroundTaskAcceptedResponse>('/routing/apply', { method: 'POST' })
}

export async function clearCidrDb(selectedFiles?: string[] | null) {
  return apiFetch<{ success: boolean; message: string }>('/routing/cidr-db/clear', {
    method: 'POST',
    body: JSON.stringify({ selected_files: selectedFiles ?? null }),
  })
}

export async function getCidrDbStatus() {
  return apiFetch<import('../types').CidrDbStatus>('/routing/cidr-db/status')
}

export async function getCidrDbStatusSummary() {
  return apiFetch<{
    success: boolean
    total_cidrs: number
    active_task?: import('../types').CidrPipelineTask | null
  }>('/routing/cidr-db/status/summary')
}

export async function getAntifilterStatus() {
  return apiFetch<import('../types').AntifilterStatus>('/routing/cidr-db/antifilter/status')
}

export async function refreshCidrDb(options?: {
  selectedFiles?: string[] | null
  retryFailedMode?: 'last' | 'selected'
  dryRun?: boolean
}) {
  return apiFetch<{ success: boolean; task_id: string; message: string }>('/routing/cidr-db/refresh', {
    method: 'POST',
    body: JSON.stringify({
      selected_files: options?.selectedFiles ?? null,
      retry_failed_mode: options?.retryFailedMode ?? null,
      dry_run: options?.dryRun ?? false,
    }),
  })
}

export async function refreshAntifilter() {
  return apiFetch<{ success: boolean; task_id: string; message: string }>('/routing/cidr-db/antifilter/refresh', {
    method: 'POST',
  })
}

export async function generateCidrFromDb(options?: {
  regions?: string[] | null
  filter_by_antifilter?: boolean
  exclude_ru_cidrs?: boolean
  apply_after?: boolean
  deploy_after?: boolean
  target_node_id?: number | null
  sync_after?: boolean
}) {
  return apiFetch<{ success: boolean; task_id: string; message: string }>('/routing/cidr-db/generate', {
    method: 'POST',
    body: JSON.stringify({
      action: 'generate',
      regions: options?.regions ?? null,
      filter_by_antifilter: options?.filter_by_antifilter ?? false,
      exclude_ru_cidrs: options?.exclude_ru_cidrs ?? false,
      apply_after: options?.apply_after ?? false,
      deploy_after: options?.deploy_after ?? false,
      target_node_id: options?.target_node_id ?? null,
      sync_after: options?.sync_after ?? false,
    }),
  })
}

export async function deployCidrToNode(options?: {
  target_node_id?: number | null
  target_node_ids?: number[] | null
  all_online?: boolean
  sync_after?: boolean
  apply_after?: boolean
  recreate_profiles_after?: boolean
  selected_files?: string[] | null
}) {
  return apiFetch<{ success: boolean; task_id: string; message: string }>('/routing/cidr-db/deploy', {
    method: 'POST',
    body: JSON.stringify({
      target_node_id: options?.target_node_id ?? null,
      target_node_ids: options?.target_node_ids ?? null,
      all_online: options?.all_online ?? false,
      sync_after: options?.sync_after ?? true,
      apply_after: options?.apply_after ?? false,
      recreate_profiles_after: options?.recreate_profiles_after ?? false,
      selected_files: options?.selected_files ?? null,
    }),
  })
}

export async function previewCidrDeploy(options?: {
  target_node_id?: number | null
  target_node_ids?: number[] | null
  all_online?: boolean
  selected_files?: string[] | null
}) {
  return apiFetch<import('../types').CidrDeployPreview>('/routing/cidr-db/deploy/preview', {
    method: 'POST',
    body: JSON.stringify({
      target_node_id: options?.target_node_id ?? null,
      target_node_ids: options?.target_node_ids ?? null,
      all_online: options?.all_online ?? false,
      selected_files: options?.selected_files ?? null,
    }),
  })
}

export async function getCidrRollbackBackups() {
  return apiFetch<{ success: boolean; backups: import('../types').CidrRuntimeBackup[] }>(
    '/routing/cidr-db/rollback/backups',
  )
}

export async function rollbackCidrFromBackup(options: {
  backup_stamp: string
  selected_files?: string[] | null
  redeploy_after?: boolean
  target_node_id?: number | null
  target_node_ids?: number[] | null
  all_online?: boolean
  sync_after?: boolean
  apply_after?: boolean
}) {
  return apiFetch<{ success: boolean; task_id: string; message: string }>('/routing/cidr-db/rollback', {
    method: 'POST',
    body: JSON.stringify({
      backup_stamp: options.backup_stamp,
      selected_files: options.selected_files ?? null,
      redeploy_after: options.redeploy_after ?? true,
      target_node_id: options.target_node_id ?? null,
      target_node_ids: options.target_node_ids ?? null,
      all_online: options.all_online ?? false,
      sync_after: options.sync_after ?? true,
      apply_after: options.apply_after ?? false,
    }),
  })
}

export async function addCustomCidrProviderEntries(
  providerKey: string,
  payload: { cidrs?: string[]; cidrs_text?: string; asns?: string[] },
) {
  return apiFetch<{
    success: boolean
    message: string
    provider_key: string
    cidrs_added: number
    asns_added: number
    total_cidrs?: number
    active_asn_count?: number
  }>(`/routing/cidr-db/providers/${encodeURIComponent(providerKey)}/custom`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getCidrBackgroundTask(taskId: string) {
  const resp = await apiFetch<
    { success?: boolean; task?: import('../types').BackgroundTask } & import('../types').BackgroundTask
  >(`/routing/cidr-db/tasks/${encodeURIComponent(taskId)}`)
  if (resp?.task?.task_id) return resp.task
  if (resp?.task_id) return resp as import('../types').BackgroundTask
  throw new ApiError('Некорректный ответ сервера о статусе задачи', 500)
}

export async function getBackgroundTask(taskId: string) {
  return apiFetch<import('../types').BackgroundTask>(`/tasks/${encodeURIComponent(taskId)}`)
}

export async function getBackgroundTaskForApiBase(taskId: string, apiBaseOverride: string) {
  return apiFetchAtBase<import('../types').BackgroundTask>(
    apiBaseOverride,
    `/tasks/${encodeURIComponent(taskId)}`,
  )
}

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

export async function resetTraffic(scope: 'all' | 'openvpn' | 'wireguard' = 'all') {
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

export async function getMonitorSettings() {
  return apiFetch<import('../types').MonitorSettings>('/settings/monitor')
}

export async function updateMonitorSettings(data: Partial<import('../types').MonitorSettings>) {
  return apiFetch<import('../types').MonitorSettings>('/settings/monitor', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function getAlertMetrics() {
  return apiFetch<import('../types').AlertMetricInfo[]>('/alert-rules/metrics')
}

export async function getAlertRules() {
  return apiFetch<import('../types').AlertRule[]>('/alert-rules')
}

export async function createAlertRule(data: import('../types').AlertRuleCreatePayload) {
  return apiFetch<import('../types').AlertRule>('/alert-rules', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateAlertRule(ruleId: number, data: Partial<import('../types').AlertRuleCreatePayload>) {
  return apiFetch<import('../types').AlertRule>(`/alert-rules/${ruleId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteAlertRule(ruleId: number) {
  return apiFetch<{ message: string }>(`/alert-rules/${ruleId}`, {
    method: 'DELETE',
  })
}

export async function getLatestChangelog() {
  return apiFetch<import('../types').LatestChangelog>('/system/latest-changelog')
}

export async function testBackupTelegram(includeConfigs = false, includeAntizapretBackup = false) {
  return apiFetch<import('../types').BackgroundTaskAcceptedResponse>('/backups/test-telegram', {
    method: 'POST',
    body: JSON.stringify({
      include_configs: includeConfigs,
      include_antizapret_backup: includeAntizapretBackup,
    }),
  })
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

export interface EditFileTransferNodeResult {
  node_id: number
  node_name: string | null
  status: 'success' | 'failed' | 'skipped'
  transferred_files: string[]
  failed?: Array<{ file: string; error: string }>
  error?: string | null
  doall_output?: string | null
}

export interface EditFileTransferResult {
  success: boolean
  message: string
  source_node_id: number
  source_node_name: string
  files: string[]
  file_keys: string[]
  run_doall: boolean
  nodes_success: number
  nodes_failed: number
  nodes_skipped: number
  total_transferred: number
  per_node: EditFileTransferNodeResult[]
}

export async function transferEditFiles(payload: {
  file_keys: string[]
  target_node_ids?: number[] | null
  all_online?: boolean
  source_node_id?: number | null
  run_doall?: boolean
  content_overrides?: Record<string, string> | null
}) {
  return apiFetch<EditFileTransferResult>('/edit-files/transfer', {
    method: 'POST',
    body: JSON.stringify(payload),
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

export async function getLightHealth() {
  return apiFetch<{
    status: string
    app: string
    env: string
    resource_profile: string
    started_at?: string
  }>('/health')
}

export async function updateFeatureToggles(toggles: Record<string, boolean>) {
  return apiFetch<import('../types').FeatureTogglesResponse>('/feature-toggles', {
    method: 'PUT',
    body: JSON.stringify({ toggles }),
  })
}

export async function getResourceProfiles() {
  return apiFetch<import('../types').ResourceProfilesResponse>('/feature-toggles/profiles')
}

export async function applyResourceProfile(profile: string) {
  return apiFetch<{
    profile: string
    requires_restart: boolean
    impact?: import('../types').ResourceProfileImpact
    workers_disabled?: string[]
    profiles: import('../types').ResourceProfilesResponse
  }>(`/feature-toggles/apply-profile?profile=${encodeURIComponent(profile)}`, {
    method: 'POST',
  })
}

export async function getRetentionSettings() {
  return apiFetch<import('../types').RetentionSettings>('/settings/retention')
}

export async function getGeoIpStatus() {
  return apiFetch<import('../types').GeoIpStatus>('/maintenance/geoip-status')
}

export async function updateRetentionSettings(data: Partial<import('../types').RetentionSettings>) {
  return apiFetch<import('../types').RetentionSettings>('/settings/retention', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function getRouteBudget() {
  return apiFetch<import('../types').RouteBudgetInfo>('/routing/cidr-db/route-budget')
}

export async function analyzeDpiLog(dpiLogText: string) {
  return apiFetch<import('../types').DpiAnalysisResult>('/routing/cidr-db/analyze-dpi', {
    method: 'POST',
    body: JSON.stringify({ dpi_log_text: dpiLogText }),
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

export async function getWarperHealth() {
  return apiFetch<import('../types').WarperHealthResponse>('/warper/health')
}

export async function getWarperStatus() {
  return apiFetch<import('../types').WarperStatusResponse>('/warper/status')
}

export async function getWarperDoctor() {
  return apiFetch<import('../types').WarperDoctorResponse>('/warper/doctor')
}

export async function postWarperToggle() {
  return apiFetch<import('../types').WarperActionResponse>('/warper/toggle', { method: 'POST' })
}

export async function getWarperDomains() {
  return apiFetch<import('../types').WarperDomainsResponse>('/warper/domains')
}

export async function addWarperDomain(domain: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/domains', {
    method: 'POST',
    body: JSON.stringify({ domain }),
  })
}

export async function removeWarperDomain(domain: string) {
  return apiFetch<import('../types').WarperActionResponse>(
    `/warper/domains/${encodeURIComponent(domain)}`,
    { method: 'DELETE' },
  )
}

export async function syncWarperDomains() {
  return apiFetch<import('../types').WarperActionResponse>('/warper/domains/sync', { method: 'POST' })
}

export async function addWarperDomainsBulk(domains: string[]) {
  return apiFetch<import('../types').WarperDomainsBulkResponse>('/warper/domains/bulk', {
    method: 'POST',
    body: JSON.stringify({ domains }),
  })
}

export async function setWarperDomainList(name: string, enable: boolean) {
  return apiFetch<import('../types').WarperActionResponse>(`/warper/domains/lists/${encodeURIComponent(name)}`, {
    method: 'POST',
    body: JSON.stringify({ enable }),
  })
}

export async function getWarperUserDomainsText() {
  return apiFetch<import('../types').WarperTextContentResponse>('/warper/domains/text')
}

export async function saveWarperUserDomainsText(text: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/domains/text', {
    method: 'PUT',
    body: JSON.stringify({ text }),
  })
}

export async function getWarperIpRanges() {
  return apiFetch<import('../types').WarperIpRangesResponse>('/warper/ip-ranges')
}

export async function addWarperIpRange(cidr: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/ip-ranges', {
    method: 'POST',
    body: JSON.stringify({ cidr }),
  })
}

export async function removeWarperIpRange(cidr: string) {
  return apiFetch<import('../types').WarperActionResponse>(
    `/warper/ip-ranges/${encodeURIComponent(cidr)}`,
    { method: 'DELETE' },
  )
}

export async function syncWarperIpRanges() {
  return apiFetch<import('../types').WarperActionResponse>('/warper/ip-ranges/sync', { method: 'POST' })
}

export async function setWarperIpRouteMode(mode: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/ip-ranges/mode', {
    method: 'POST',
    body: JSON.stringify({ mode }),
  })
}

export async function setWarperIpExport(enable: boolean) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/ip-ranges/export', {
    method: 'POST',
    body: JSON.stringify({ enable }),
  })
}

export async function getWarperIpRangesText() {
  return apiFetch<import('../types').WarperTextContentResponse>('/warper/ip-ranges/text')
}

export async function saveWarperIpRangesText(text: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/ip-ranges/text', {
    method: 'PUT',
    body: JSON.stringify({ text }),
  })
}

export async function getWarperTraffic(period: import('../types').WarperTrafficPeriod = 'today') {
  return apiFetch<import('../types').WarperTrafficResponse>(`/warper/traffic?period=${encodeURIComponent(period)}`)
}

export async function getWarperLogs(lines = 200) {
  return apiFetch<import('../types').WarperLogsResponse>(`/warper/logs?lines=${lines}`)
}

export async function getWarperMode() {
  return apiFetch<import('../types').WarperModeResponse>('/warper/settings/mode')
}

export async function getWarperSettingsOptions() {
  return apiFetch<import('../types').WarperSettingsOptionsResponse>('/warper/settings/options')
}

export async function setWarperModeWarp(keySource?: 'system' | 'generate' | null) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/mode/warp', {
    method: 'POST',
    body: JSON.stringify({ key_source: keySource ?? null }),
  })
}

export async function setWarperModeSlave(host: string, port: number, key: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/mode/slave', {
    method: 'POST',
    body: JSON.stringify({ host, port, key }),
  })
}

export async function setWarperModeWg(configPath: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/mode/wg', {
    method: 'POST',
    body: JSON.stringify({ config_path: configPath }),
  })
}

export async function setWarperFullVpn(enable: boolean) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/fullvpn', {
    method: 'PUT',
    body: JSON.stringify({ enable }),
  })
}

export async function setWarperSubnet(subnet: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/subnet', {
    method: 'PUT',
    body: JSON.stringify({ subnet }),
  })
}

export async function setWarperMtu(mtu: number) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/mtu', {
    method: 'PUT',
    body: JSON.stringify({ mtu }),
  })
}

export async function setWarperLogLevel(level: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/log-level', {
    method: 'PUT',
    body: JSON.stringify({ level }),
  })
}

export async function postWarperSingbox(action: 'start' | 'stop' | 'restart') {
  return apiFetch<import('../types').WarperActionResponse>(`/warper/singbox/${action}`, { method: 'POST' })
}

export async function searchWarperCatalog(query = '') {
  const params = query.trim() ? `?query=${encodeURIComponent(query.trim())}` : ''
  return apiFetch<import('../types').WarperCatalogSearchResponse>(`/warper/catalog/search${params}`)
}

export async function getWarperCatalogInstalled() {
  return apiFetch<import('../types').WarperCatalogInstalledResponse>('/warper/catalog/installed')
}

export async function showWarperCatalog(name: string) {
  return apiFetch<import('../types').WarperCatalogShowResponse>(`/warper/catalog/show/${encodeURIComponent(name)}`)
}

export async function addWarperCatalog(name: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/catalog/add', {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
}

export async function removeWarperCatalog(name: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/catalog/remove', {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
}

export async function updateWarperCatalog(name = '') {
  const params = name.trim() ? `?name=${encodeURIComponent(name.trim())}` : ''
  return apiFetch<import('../types').WarperActionResponse>(`/warper/catalog/update${params}`, { method: 'POST' })
}

export async function refreshWarperCatalog() {
  return apiFetch<import('../types').WarperActionResponse>('/warper/catalog/refresh', { method: 'POST' })
}

export async function checkWarperUpdates(force = false) {
  const params = force ? '?force=true' : ''
  return apiFetch<import('../types').WarperUpdatesCheckResponse>(`/warper/updates/check${params}`)
}

export async function applyWarperUpdate(timeout = 600) {
  return apiFetch<import('../types').WarperActionResponse>(`/warper/updates/apply?timeout=${timeout}`, {
    method: 'POST',
  })
}

export function openWarperUpdateStream(
  onEvent: (event: import('../types').WarperUpdateStreamEvent) => void,
  onError?: (message: string) => void,
): EventSource | null {
  const token = getToken()
  if (!token) return null
  const url = `${API_BASE}/warper/updates/stream?token=${encodeURIComponent(token)}`
  const source = new EventSource(url)
  source.onmessage = (event) => {
    try {
      onEvent(JSON.parse(event.data) as import('../types').WarperUpdateStreamEvent)
    } catch {
      onError?.('Ошибка разбора потока обновления AZ-WARP')
    }
  }
  source.onerror = () => {
    onError?.('Соединение с потоком обновления прервано')
  }
  return source
}

export async function getSecuritySettings() {
  return apiFetch<import('../types').SecuritySettings>('/security')
}

export async function getSecretsRotationCatalog() {
  return apiFetch<import('../types').SecretRotationItem[]>('/security/secrets-rotation')
}

export async function previewSecretsRotation(secretId: string, value?: string) {
  return apiFetch<import('../types').SecretRotationPreview>('/security/secrets-rotation/preview', {
    method: 'POST',
    body: JSON.stringify({ secret_id: secretId, value: value || undefined }),
  })
}

export async function applySecretsRotation(payload: {
  secret_id: string
  new_value: string
  preview_token: string
  confirm: string
}) {
  return apiFetch<import('../types').SecretRotationApplyResult>('/security/secrets-rotation/apply', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function updateSecuritySettings(
  data: Partial<import('../types').SecuritySettings & { qr_download_pin?: string }>,
) {
  return apiFetch<import('../types').SecuritySettings>('/security', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function addTempWhitelist(ip: string, hours: number) {
  return apiFetch<import('../types').SecuritySettings>('/security/temp-whitelist', {
    method: 'POST',
    body: JSON.stringify({ ip, hours }),
  })
}

export async function removeTempWhitelist(ip: string) {
  return apiFetch<import('../types').SecuritySettings>(
    `/security/temp-whitelist/${encodeURIComponent(ip)}`,
    { method: 'DELETE' },
  )
}

export async function getClientIp() {
  return apiFetch<{ client_ip: string; allowed: boolean }>('/security/check-ip')
}

export async function togglePublicDownload(enabled?: boolean) {
  return apiFetch<{ enabled: boolean; message: string }>('/security/public-download', {
    method: 'POST',
    body: JSON.stringify(enabled === undefined ? {} : { enabled }),
  })
}

export async function getOpenVpnGroup() {
  return apiFetch<import('../types').OpenVpnGroupState>('/configs/openvpn-group')
}

export async function setOpenVpnGroup(group: string) {
  return apiFetch<import('../types').OpenVpnGroupState>('/configs/openvpn-group', {
    method: 'PUT',
    body: JSON.stringify({ group }),
  })
}

export async function getServerMetrics(accurate = false) {
  return apiFetch<import('../types').ServerMetrics>(`/server-monitor/metrics?accurate=${accurate}`)
}

export async function getServerInterfaces() {
  return apiFetch<{
    interfaces: string[]
    groups?: Record<string, string[]>
    primary_interface?: string | null
  }>('/server-monitor/interfaces')
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

export async function runSiteDiagnostics() {
  return apiFetch<import('../types').SiteDiagnosticsReport>('/site-diagnostics/run', {
    method: 'POST',
  })
}

export async function applySystemUpdate() {
  return apiFetch<import('../types').BackgroundTaskAcceptedResponse>('/system/update', { method: 'POST' })
}

export async function restartPanel() {
  return apiFetch<{ message: string }>('/system/restart', { method: 'POST' })
}

export async function rebuildPanel() {
  return apiFetch<import('../types').BackgroundTaskAcceptedResponse>('/system/rebuild', { method: 'POST' })
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

export async function clearScannerBans() {
  return apiFetch<{ message: string }>('/security/scanner-bans/clear', { method: 'POST' })
}

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

export async function checkSystemUpdates() {
  return apiFetch<{ updates_available: boolean; commits_behind: number; local_hash?: string }>('/system/updates')
}

export function downloadBackup(fileName: string) {
  const token = getToken()
  const url = `${API_BASE}/backups/${encodeURIComponent(fileName)}/download`
  return fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
}

export type QrContentMode = 'profile' | 'download-link'

export type QrBlobResult = {
  blob: Blob
  contentMode: QrContentMode
  downloadUrl?: string
}

async function parseApiError(response: Response, fallback: string): Promise<ApiError> {
  const body = await response.text()
  const detail = parseHttpErrorBody(body, response.status, fallback)
  return new ApiError(detail, response.status)
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
