import { ApiError } from '@/api/client'
import { parseHttpErrorBody } from '@/lib/httpErrorMessage'
import {
  getTelegramWebApp,
  resolveTelegramInitData,
  waitForTelegramInitData,
} from '@/tg-mini/lib/telegramInitData'
import type {
  AdminNotifySettings,
  ClosedAccessView,
  FeatureModulesResponse,
  InstallPlatform,
  SelfServiceLimits,
  SelfServiceQuota,
  TelegramSettings,
  TgMiniAuthResponse,
  TgMiniConfig,
  TgMiniConfigFile,
  TgMeConfig,
  TgMeStatus,
  TgMiniNodeActionResponse,
  TgMiniNodesResponse,
  TgMiniQrLink,
  TgMiniSettings,
  User,
  VpnConfig,
  VpnType,
  ClientTemplate,
  ClientAccessPolicy,
  UnlockCodeRecord,
  ClientPoliciesResponseEntry,
  AccessRequestResponse,
  ApproveRequest,
  RejectRequest,
  PresetResponse,
  UserProvisionedCreate,
  UserProvisionedResponse,
  UserHistoryEntry,
  UserStatsResponse,
  UserUpdatePayload,
} from '@/types'
import { apiBase } from '@/lib/panelBase'

const API_BASE = `${apiBase}/tg-mini`
const PANEL_API_BASE = apiBase
const LEGACY_TOKEN_KEY = 'tg_token'

/** Kept in memory only: Telegram re-sends initData on every launch, so a persisted JWT buys nothing. */
let tgToken: string | null = null
let refreshInFlight: Promise<boolean> | null = null

try {
  localStorage.removeItem(LEGACY_TOKEN_KEY)
} catch {
  // storage may be unavailable in the Telegram WebView
}

export function getTgToken(): string | null {
  return tgToken
}

export function setTgToken(token: string): void {
  tgToken = token
}

export function clearTgToken(): void {
  tgToken = null
}

async function parseApiResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.text()
    const detail = parseHttpErrorBody(body, response.status)
    throw new ApiError(detail, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

type RequestTarget = { base?: string; retry?: boolean }

async function request(
  path: string,
  options: RequestInit = {},
  { base = PANEL_API_BASE, retry = true }: RequestTarget = {},
): Promise<Response> {
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getTgToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(`${base}${path}`, { ...options, headers })
  if (response.status === 401 && retry && (await renewAfterUnauthorized(token))) {
    return request(path, options, { base, retry: false })
  }
  return response
}

async function requestJson<T>(
  path: string,
  options: RequestInit = {},
  target: RequestTarget = {},
): Promise<T> {
  return parseApiResponse<T>(await request(path, options, target))
}

async function tgFetch<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  return requestJson<T>(path, options, { base: API_BASE, retry: retry && path !== '/auth' })
}

/** Mini App token is accepted only by backend endpoints marked `@tg_mini_token_allowed` (401 otherwise). */
async function panelApiFetch<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  return requestJson<T>(path, options, { retry })
}

/** Raw panel response (blobs, images) with the Mini App token. */
async function panelApiFetchResponse(
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<Response> {
  const response = await request(path, options, { retry })
  if (!response.ok) {
    const body = await response.text()
    throw new ApiError(parseHttpErrorBody(body, response.status), response.status)
  }
  return response
}

export async function refreshTgSessionFromInitData(initData: string): Promise<void> {
  try {
    const auth = await tgAuth(initData)
    setTgToken(auth.access_token)
  } catch (err) {
    clearTgToken()
    throw err
  }
}

async function renewTgSession(): Promise<boolean> {
  const tg = getTelegramWebApp()
  let initData = resolveTelegramInitData(tg)
  if (!initData) {
    initData = await waitForTelegramInitData(tg)
  }
  if (!initData) {
    clearTgToken()
    return false
  }
  await refreshTgSessionFromInitData(initData)
  return true
}

/** Re-issue JWT from Telegram initData; parallel callers share one /auth round-trip. */
export function refreshTgSession(): Promise<boolean> {
  refreshInFlight ??= renewTgSession().finally(() => {
    refreshInFlight = null
  })
  return refreshInFlight
}

/** After a 401: reuse a token another request already renewed, otherwise renew once for everyone. */
async function renewAfterUnauthorized(sentToken: string | null): Promise<boolean> {
  const current = getTgToken()
  if (current && current !== sentToken) return true
  return refreshTgSession()
}

async function tgAuth(initData: string): Promise<TgMiniAuthResponse> {
  const response = await fetch(`${API_BASE}/auth`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ init_data: initData }),
  })
  return parseApiResponse<TgMiniAuthResponse>(response)
}

export async function getTgConfigs(): Promise<{ configs: TgMiniConfig[] }> {
  return tgFetch<{ configs: TgMiniConfig[] }>('/configs')
}

export async function getTgMeConfigs(): Promise<{
  configs: TgMeConfig[]
  closed_access: ClosedAccessView | null
  status: TgMeStatus
}> {
  return tgFetch<{
    configs: TgMeConfig[]
    closed_access: ClosedAccessView | null
    status: TgMeStatus
  }>('/me/configs')
}

/** Продление доступа unlock-кодом (owner scope) — Mini App. */
export async function redeemTgMeCode(code: string): Promise<{
  grant_days: number
  protocols_applied: string[]
  access_until_by_protocol: Record<string, string | null>
}> {
  return tgFetch<{
    grant_days: number
    protocols_applied: string[]
    access_until_by_protocol: Record<string, string | null>
  }>('/me/redeem-code', {
    method: 'POST',
    body: JSON.stringify({ code }),
  })
}

/** Самосервис плана конфигов: добавить следующее свободное имя. */
export async function createTgMePlanConfig(): Promise<{ index: number; task_id: string }> {
  return panelApiFetch<{ index: number; task_id: string }>('/me/plan-configs', {
    method: 'POST',
  })
}

/** Самосервис плана конфигов: убрать имя по индексу. */
export async function removeTgMePlanConfig(
  index: number,
  confirmDeletions = false,
): Promise<{ task_id: string }> {
  const qs = confirmDeletions ? '?confirm_deletions=true' : ''
  return panelApiFetch<{ task_id: string }>(`/me/plan-configs/${index}${qs}`, {
    method: 'DELETE',
  })
}

export async function getTgConfigFiles(configId: number): Promise<{ files: TgMiniConfigFile[] }> {
  // /me/... ищет конфиг на его собственном узле; /configs/{id}/files работает
  // только с активным узлом и даёт 404 для конфига на другом сервере.
  return tgFetch<{ files: TgMiniConfigFile[] }>(`/me/configs/${configId}/files`)
}

export async function sendTgConfig(
  configId: number,
  data: { path?: string; destination: 'self' | 'owner'; platform?: InstallPlatform },
): Promise<{ message: string }> {
  return tgFetch<{ message: string }>(`/me/configs/${configId}/send`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getTgQrLink(configId: number, path: string): Promise<TgMiniQrLink> {
  const params = new URLSearchParams({ config_id: String(configId), path })
  return tgFetch<TgMiniQrLink>(`/me/qr-link?${params.toString()}`)
}

export async function getTgSettings(opts?: { retry?: boolean }): Promise<TgMiniSettings> {
  return tgFetch<TgMiniSettings>('/settings', {}, opts?.retry ?? true)
}

export async function getTgAdminNotify(): Promise<AdminNotifySettings> {
  return tgFetch<AdminNotifySettings>('/admin-notify')
}

export async function updateTgAdminNotify(data: {
  telegram_id?: string
  events?: Record<string, boolean>
  recipient_user_ids?: number[]
  node_offline_grace_seconds?: number
}): Promise<AdminNotifySettings> {
  return tgFetch<AdminNotifySettings>('/admin-notify', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function testTgAdminNotify(): Promise<{ message: string }> {
  return tgFetch<{ message: string }>('/admin-notify/test', { method: 'POST' })
}

export async function getTgTelegramSettings(): Promise<TelegramSettings> {
  return tgFetch<TelegramSettings>('/telegram-settings')
}

export async function updateTgTelegramSettings(data: {
  bot_token?: string
  bot_username?: string
  auth_max_age_seconds?: number
  chat_id?: string
  notify_enabled?: boolean
  notify_on_backup?: boolean
  bot_command_rate_max?: number
  bot_command_rate_window_seconds?: number
}): Promise<TelegramSettings> {
  return tgFetch<TelegramSettings>('/telegram-settings', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function getTgSelfServiceLimits(): Promise<SelfServiceLimits> {
  return tgFetch<SelfServiceLimits>('/self-service')
}

export async function updateTgSelfServiceLimits(data: Partial<SelfServiceLimits>): Promise<SelfServiceLimits> {
  return tgFetch<SelfServiceLimits>('/self-service', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function testTgTelegram(): Promise<{ message: string }> {
  return tgFetch<{ message: string }>('/telegram-settings/test', { method: 'POST' })
}

export async function getTgNodes(): Promise<TgMiniNodesResponse> {
  return tgFetch<TgMiniNodesResponse>('/nodes')
}

export async function checkTgNodeHealth(nodeId: number): Promise<TgMiniNodeActionResponse> {
  return tgFetch<TgMiniNodeActionResponse>(`/nodes/${nodeId}/health`, { method: 'POST' })
}

export async function activateTgNode(nodeId: number): Promise<TgMiniNodeActionResponse> {
  return tgFetch<TgMiniNodeActionResponse>(`/nodes/${nodeId}/activate`, { method: 'POST' })
}

export async function getTgFeatureModules(): Promise<FeatureModulesResponse> {
  return panelApiFetch<FeatureModulesResponse>('/feature-modules')
}

export async function getTgConfigQuota(): Promise<SelfServiceQuota> {
  return panelApiFetch<SelfServiceQuota>('/configs/quota')
}

export async function getTgPanelConfig(configId: number): Promise<VpnConfig> {
  return panelApiFetch<VpnConfig>(`/configs/${configId}?include_files=false`)
}

export async function createTgPanelConfig(data: {
  client_name: string
  vpn_type: VpnType
  cert_expire_days?: number
  description?: string
  owner_id?: number
  ttl?: string
}): Promise<VpnConfig> {
  return panelApiFetch<VpnConfig>('/configs', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateTgPanelConfig(
  configId: number,
  data: { description?: string; cert_expire_days?: number; owner_id?: number },
): Promise<VpnConfig> {
  return panelApiFetch<VpnConfig>(`/configs/${configId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteTgPanelConfig(configId: number): Promise<{ message: string }> {
  return panelApiFetch<{ message: string }>(`/configs/${configId}`, { method: 'DELETE' })
}

export async function getTgPanelUsers(): Promise<User[]> {
  return panelApiFetch<User[]>('/users')
}

export async function getTgClientTemplates(): Promise<ClientTemplate[]> {
  return panelApiFetch<ClientTemplate[]>('/client-templates')
}

export async function applyTgClientTemplate(
  templateId: number,
  data: { client_name: string; owner_id?: number },
): Promise<VpnConfig> {
  return panelApiFetch<VpnConfig>(`/client-templates/${templateId}/apply`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getTgClientPolicy(
  clientName: string,
  vpnType: VpnType,
): Promise<ClientAccessPolicy | null> {
  const params = new URLSearchParams({ clients: clientName })
  const data = await panelApiFetch<Record<string, ClientPoliciesResponseEntry>>(
    `/client-access/policies?${params.toString()}`,
  )
  const entry = data[clientName]
  if (!entry) return null
  if (vpnType === 'openvpn') return entry.openvpn
  if (vpnType === 'amneziawg2') return entry.amneziawg2 ?? null
  return entry.wireguard
}

async function postClientAccess(path: string, clientName: string, extra?: Record<string, unknown>) {
  return panelApiFetch(path, {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName, ...extra }),
  })
}

export async function tgOpenvpnTempBlock(clientName: string, days: number) {
  return postClientAccess('/client-access/openvpn/temp-block', clientName, { days })
}

export async function tgOpenvpnPermanentBlock(clientName: string) {
  return postClientAccess('/client-access/openvpn/permanent-block', clientName)
}

export async function tgOpenvpnUnblock(clientName: string) {
  return postClientAccess('/client-access/openvpn/unblock', clientName)
}

export async function tgWgTempBlock(clientName: string, days: number) {
  return postClientAccess('/client-access/wireguard/temp-block', clientName, { days })
}

export async function tgWgPermanentBlock(clientName: string) {
  return postClientAccess('/client-access/wireguard/permanent-block', clientName)
}

export async function tgWgUnblock(clientName: string) {
  return postClientAccess('/client-access/wireguard/unblock', clientName)
}

export async function tgOpenvpnSetTrafficLimit(
  clientName: string,
  limitValue: number,
  limitUnit = 'MB',
  limitPeriodDays?: number | null,
) {
  return postClientAccess('/client-access/openvpn/set-traffic-limit', clientName, {
    limit_value: limitValue,
    limit_unit: limitUnit,
    limit_period_days: limitPeriodDays ?? null,
  })
}

export async function tgWgSetTrafficLimit(
  clientName: string,
  limitValue: number,
  limitUnit = 'MB',
  limitPeriodDays?: number | null,
) {
  return postClientAccess('/client-access/wireguard/set-traffic-limit', clientName, {
    limit_value: limitValue,
    limit_unit: limitUnit,
    limit_period_days: limitPeriodDays ?? null,
  })
}

export async function tgAwg2SetTrafficLimit(
  clientName: string,
  limitValue: number,
  limitUnit = 'MB',
  limitPeriodDays?: number | null,
) {
  return postClientAccess('/client-access/amneziawg2/set-traffic-limit', clientName, {
    limit_value: limitValue,
    limit_unit: limitUnit,
    limit_period_days: limitPeriodDays ?? null,
  })
}

export type UnlockCodeProtocol = 'openvpn' | 'wireguard' | 'amneziawg2'

export async function setTgClientAccessUntil(
  protocol: UnlockCodeProtocol,
  clientName: string,
  accessUntil: string | null,
) {
  return panelApiFetch<{ access_until: string | null }>(
    `/client-access/${protocol}/${encodeURIComponent(clientName)}/access-until`,
    {
      method: 'PATCH',
      body: JSON.stringify({ access_until: accessUntil }),
    },
  )
}

export async function getTgUnlockCodes(includeRevoked = false): Promise<UnlockCodeRecord[]> {
  const params = new URLSearchParams()
  if (includeRevoked) params.set('include_revoked', 'true')
  const query = params.toString()
  return panelApiFetch<UnlockCodeRecord[]>(`/unlock-codes${query ? `?${query}` : ''}`)
}

export async function createTgUnlockCode(payload: {
  grant_days: number
  protocols: UnlockCodeProtocol[]
  mode: 'single' | 'multi'
  max_redemptions?: number
  code_expires_at?: string | null
  code?: string | null
  allowed_client_names?: string[]
}): Promise<UnlockCodeRecord> {
  return panelApiFetch<UnlockCodeRecord>('/unlock-codes', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function revokeTgUnlockCode(codeId: number): Promise<{ ok: boolean; id: number }> {
  return panelApiFetch<{ ok: boolean; id: number }>(`/unlock-codes/${codeId}/revoke`, {
    method: 'POST',
  })
}

/* ------------------- Админ: конфиги на активном узле ------------------- */

/** Файлы профиля на активном узле (админский список конфигов). */
export async function getTgPanelConfigFiles(
  configId: number,
): Promise<{ files: TgMiniConfigFile[] }> {
  return tgFetch<{ files: TgMiniConfigFile[] }>(`/configs/${configId}/files`)
}

export async function sendTgPanelConfig(
  configId: number,
  data: { path?: string; destination: 'self' | 'owner'; platform?: InstallPlatform },
): Promise<{ message: string }> {
  return tgFetch<{ message: string }>(`/configs/${configId}/send`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getTgPanelQrLink(configId: number, path: string): Promise<TgMiniQrLink> {
  const params = new URLSearchParams({ config_id: String(configId), path })
  return tgFetch<TgMiniQrLink>(`/qr-link?${params.toString()}`)
}

/* ------------------- Клиенты: аккаунты абонентов ------------------- */

export async function suspendTgUser(userId: number, reason?: string | null): Promise<User> {
  return panelApiFetch<User>(`/users/${userId}/suspend`, {
    method: 'POST',
    body: JSON.stringify({ reason: reason ?? null }),
  })
}

export async function resumeTgUser(userId: number): Promise<User> {
  return panelApiFetch<User>(`/users/${userId}/resume`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export async function extendTgUser(userId: number, days: number): Promise<User> {
  return panelApiFetch<User>(`/users/${userId}/extend`, {
    method: 'POST',
    body: JSON.stringify({ days }),
  })
}

export async function resetTgUserTraffic(userId: number): Promise<User> {
  return panelApiFetch<User>(`/users/${userId}/traffic-counter/reset`, { method: 'POST' })
}

export async function setTgUserTrafficLimit(
  userId: number,
  bytes: number | null,
): Promise<User> {
  return panelApiFetch<User>(`/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify({ traffic_limit_bytes: bytes }),
  })
}

export async function deleteTgUser(userId: number): Promise<{ message: string }> {
  return panelApiFetch<{ message: string }>(`/users/${userId}`, { method: 'DELETE' })
}

export async function createTgProvisionedUser(
  data: UserProvisionedCreate,
): Promise<UserProvisionedResponse> {
  return panelApiFetch<UserProvisionedResponse>('/users/provisioned', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function listTgPresets(): Promise<PresetResponse[]> {
  return panelApiFetch<PresetResponse[]>('/users/presets')
}

/* ------------------- Подтверждение доступа: заявки ------------------- */

export async function listTgRequests(params?: {
  status?: string
  type?: string
  q?: string
  limit?: number
  offset?: number
}): Promise<AccessRequestResponse[]> {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  if (params?.type) qs.set('type', params.type)
  if (params?.q) qs.set('q', params.q)
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.offset) qs.set('offset', String(params.offset))
  const query = qs.toString()
  return panelApiFetch<AccessRequestResponse[]>(`/users/requests${query ? `?${query}` : ''}`)
}

export async function getTgRequestsCount(status = 'pending'): Promise<number> {
  const data = await panelApiFetch<{ count: number }>(
    `/users/requests/count?status=${encodeURIComponent(status)}`,
  )
  return data.count
}

export async function approveTgRequest(
  requestId: number,
  data: ApproveRequest,
): Promise<AccessRequestResponse> {
  return panelApiFetch<AccessRequestResponse>(`/users/requests/${requestId}/approve`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function rejectTgRequest(
  requestId: number,
  data: RejectRequest,
): Promise<AccessRequestResponse> {
  return panelApiFetch<AccessRequestResponse>(`/users/requests/${requestId}/reject`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/** Чек оплаты заявки (JPEG) для предпросмотра. */
export async function getTgRequestReceipt(requestId: number): Promise<Blob> {
  const response = await panelApiFetchResponse(`/users/requests/${requestId}/receipt`)
  return response.blob()
}

/* ------------------- Карточка клиента: права, история, статистика ------------------- */

export async function updateTgUser(userId: number, payload: UserUpdatePayload): Promise<User> {
  return panelApiFetch<User>(`/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function getTgUserHistory(
  userId: number,
  limit = 50,
): Promise<UserHistoryEntry[]> {
  return panelApiFetch<UserHistoryEntry[]>(`/users/${userId}/history?limit=${limit}`)
}

export async function getTgUserStats(userId: number, days = 30): Promise<UserStatsResponse> {
  return panelApiFetch<UserStatsResponse>(`/users/${userId}/stats?days=${days}`)
}
