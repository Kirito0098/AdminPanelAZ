import { apiFetch } from './http'
import type {
  AppSettings,
  User,
  UserRole,
  UserUpdatePayload,
  EventWebhookSettings,
  AuditStreamSettings,
  BackgroundTaskAcceptedResponse,
  MonitorSettings,
  AlertMetricInfo,
  AlertRule,
  AlertRuleCreatePayload,
  LatestChangelog,
  FeatureModulesResponse,
  FeatureTogglesResponse,
  ResourceProfilesResponse,
  ResourceProfileImpact,
  RetentionSettings,
  GeoIpStatus,
  RouteBudgetInfo,
  SecuritySettings,
  SecretRotationItem,
  SecretRotationPreview,
  SecretRotationApplyResult,
  PortalPublishStatus,
} from '../types'

export async function getSettings() {
  return apiFetch<AppSettings>('/settings')
}

export async function updateSettings(data: Partial<AppSettings>) {
  return apiFetch<AppSettings>('/settings', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function getUsers() {
  return apiFetch<User[]>('/users')
}

export async function createUser(data: {
  username: string
  password: string
  role: UserRole
}) {
  return apiFetch<User>('/users', {
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

export async function updateUser(id: number, data: UserUpdatePayload) {
  return apiFetch<User>(`/users/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function getEventWebhookSettings() {
  return apiFetch<EventWebhookSettings>('/security/event-webhooks')
}

export async function updateEventWebhookSettings(data: {
  url?: string
  secret?: string
  enabled?: boolean
  events?: Array<{ key: string; enabled: boolean }>
}) {
  return apiFetch<EventWebhookSettings>('/security/event-webhooks', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function getAuditStreamSettings() {
  return apiFetch<AuditStreamSettings>('/security/audit-stream')
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
  return apiFetch<AuditStreamSettings>('/security/audit-stream', {
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
  return apiFetch<BackgroundTaskAcceptedResponse>('/settings/run-doall', { method: 'POST' })
}

export async function restartService(serviceName: string) {
  return apiFetch<{ message: string; detail?: string }>('/settings/restart-service', {
    method: 'POST',
    body: JSON.stringify({ service_name: serviceName }),
  })
}

export async function getMonitorSettings() {
  return apiFetch<MonitorSettings>('/settings/monitor')
}

export async function updateMonitorSettings(data: Partial<MonitorSettings>) {
  return apiFetch<MonitorSettings>('/settings/monitor', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function getAlertMetrics() {
  return apiFetch<AlertMetricInfo[]>('/alert-rules/metrics')
}

export async function getAlertRules() {
  return apiFetch<AlertRule[]>('/alert-rules')
}

export async function createAlertRule(data: AlertRuleCreatePayload) {
  return apiFetch<AlertRule>('/alert-rules', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateAlertRule(ruleId: number, data: Partial<AlertRuleCreatePayload>) {
  return apiFetch<AlertRule>(`/alert-rules/${ruleId}`, {
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
  return apiFetch<LatestChangelog>('/system/latest-changelog')
}

export async function getFeatureModules() {
  return apiFetch<FeatureModulesResponse>('/feature-modules')
}

export async function getFeatureToggles() {
  return apiFetch<FeatureTogglesResponse>('/feature-toggles')
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
  return apiFetch<FeatureTogglesResponse>('/feature-toggles', {
    method: 'PUT',
    body: JSON.stringify({ toggles }),
  })
}

export async function getResourceProfiles() {
  return apiFetch<ResourceProfilesResponse>('/feature-toggles/profiles')
}

export async function applyResourceProfile(profile: string) {
  return apiFetch<{
    profile: string
    requires_restart: boolean
    impact?: ResourceProfileImpact
    workers_disabled?: string[]
    profiles: ResourceProfilesResponse
  }>(`/feature-toggles/apply-profile?profile=${encodeURIComponent(profile)}`, {
    method: 'POST',
  })
}

export async function getRetentionSettings() {
  return apiFetch<RetentionSettings>('/settings/retention')
}

export async function getGeoIpStatus() {
  return apiFetch<GeoIpStatus>('/maintenance/geoip-status')
}

export async function updateRetentionSettings(data: Partial<RetentionSettings>) {
  return apiFetch<RetentionSettings>('/settings/retention', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function getRouteBudget() {
  return apiFetch<RouteBudgetInfo>('/routing/cidr-db/route-budget')
}

export async function getSecuritySettings() {
  return apiFetch<SecuritySettings>('/security')
}

export async function getSecretsRotationCatalog() {
  return apiFetch<SecretRotationItem[]>('/security/secrets-rotation')
}

export async function previewSecretsRotation(secretId: string, value?: string) {
  return apiFetch<SecretRotationPreview>('/security/secrets-rotation/preview', {
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
  return apiFetch<SecretRotationApplyResult>('/security/secrets-rotation/apply', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function updateSecuritySettings(
  data: Partial<SecuritySettings & { qr_download_pin?: string }>,
) {
  return apiFetch<SecuritySettings>('/security', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function getPortalPublishStatus() {
  return apiFetch<PortalPublishStatus>('/security/portal-publish-status')
}

export async function publishPortalDomain(data: {
  portal_domain: string
  email?: string | null
  save_domain?: boolean
}) {
  return apiFetch<BackgroundTaskAcceptedResponse>('/security/portal-publish', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function checkPortalReadiness(data: {
  portal_domain: string
  save_domain?: boolean
}) {
  return apiFetch<BackgroundTaskAcceptedResponse>('/security/portal-readiness-check', {
    method: 'POST',
    body: JSON.stringify({ save_domain: false, ...data }),
  })
}

export async function preparePortalReadiness(data: {
  portal_domain: string
  save_domain?: boolean
}) {
  return apiFetch<BackgroundTaskAcceptedResponse>('/security/portal-readiness-prepare', {
    method: 'POST',
    body: JSON.stringify({ save_domain: true, ...data }),
  })
}

export async function addTempWhitelist(ip: string, hours: number) {
  return apiFetch<SecuritySettings>('/security/temp-whitelist', {
    method: 'POST',
    body: JSON.stringify({ ip, hours }),
  })
}

export async function removeTempWhitelist(ip: string) {
  return apiFetch<SecuritySettings>(
    `/security/temp-whitelist/${encodeURIComponent(ip)}`,
    { method: 'DELETE' },
  )
}

export async function getClientIp() {
  return apiFetch<{ client_ip: string; allowed: boolean }>('/security/check-ip')
}
