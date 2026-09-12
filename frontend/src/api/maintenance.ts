import {
  API_BASE,
  apiFetch,
  getToken,
} from './http'

export async function getBackups() {
  return apiFetch<import('../types').BackupEntry[]>('/backups')
}

export async function createBackup(
  includeConfigs = false,
  includeAntizapretBackup = false,
  sendToTelegram = false,
  includeAwg2Backup = false,
) {
  return apiFetch<import('../types').BackupEntry>('/backups/create', {
    method: 'POST',
    body: JSON.stringify({
      include_configs: includeConfigs,
      include_antizapret_backup: includeAntizapretBackup,
      include_awg2_backup: includeAwg2Backup,
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

export async function getDdnsSettings() {
  return apiFetch<import('../types').DdnsSettings>('/settings/vpn-network/ddns')
}

export async function updateDdnsSettings(data: import('../types').DdnsSettingsUpdatePayload) {
  return apiFetch<import('../types').DdnsActionResponse>('/settings/vpn-network/ddns', {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function runDdnsUpdate() {
  return apiFetch<import('../types').DdnsActionResponse>('/settings/vpn-network/ddns/update', {
    method: 'POST',
  })
}

export async function getCloudflareProxySettings() {
  return apiFetch<import('../types').CloudflareProxySettings>('/settings/cloudflare-proxy')
}

export async function updateCloudflareProxySettings(
  data: import('../types').CloudflareProxySettingsUpdatePayload,
) {
  return apiFetch<import('../types').CloudflareProxySettings>('/settings/cloudflare-proxy', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function refreshCloudflareProxy(force = false) {
  return apiFetch<import('../types').CloudflareProxyRefreshResponse>('/settings/cloudflare-proxy/refresh', {
    method: 'POST',
    body: JSON.stringify({ force }),
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
  node_offline_grace_seconds?: number
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

export async function getOpenVpnGroup() {
  return apiFetch<import('../types').OpenVpnGroupState>('/configs/openvpn-group')
}

export async function setOpenVpnGroup(group: string) {
  return apiFetch<import('../types').OpenVpnGroupState>('/configs/openvpn-group', {
    method: 'PUT',
    body: JSON.stringify({ group }),
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

export async function scheduleServerReboot(nodeId: number, confirm: 'REBOOT') {
  return apiFetch<import('../types').ServerRebootScheduleResponse>('/settings/reboot', {
    method: 'POST',
    body: JSON.stringify({ node_id: nodeId, confirm }),
  })
}

export async function cancelServerReboot(rebootId: string) {
  return apiFetch<import('../types').ServerRebootPendingItem>(
    `/settings/reboot/${rebootId}/cancel`,
    { method: 'POST' },
  )
}

export async function getPendingServerReboots() {
  return apiFetch<import('../types').ServerRebootPendingResponse>('/settings/reboot/pending')
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

export async function checkSystemUpdates() {
  return apiFetch<{ updates_available: boolean; commits_behind: number; local_hash?: string }>('/system/updates')
}

export function downloadBackup(fileName: string) {
  const token = getToken()
  const url = `${API_BASE}/backups/${encodeURIComponent(fileName)}/download`
  return fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
}
