import { apiFetch } from './http'

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

export async function getUserConfigAccess(userId: number) {
  return apiFetch<{ user_id: number; config_groups: string[] }>(`/users/${userId}/config-access`)
}

export async function setUserConfigAccess(userId: number, configGroups: string[]) {
  return apiFetch<{ message: string }>(`/users/${userId}/config-access`, {
    method: 'PUT',
    body: JSON.stringify({ config_groups: configGroups }),
  })
}

export async function updateUser(id: number, data: Record<string, unknown>) {
  return apiFetch<import('../types').User>(`/users/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
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

export async function getPortalPublishStatus() {
  return apiFetch<import('../types').PortalPublishStatus>('/security/portal-publish-status')
}

export async function publishPortalDomain(data: {
  portal_domain: string
  email?: string | null
  save_domain?: boolean
}) {
  return apiFetch<import('../types').BackgroundTaskAcceptedResponse>('/security/portal-publish', {
    method: 'POST',
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
