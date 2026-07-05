import { ApiError } from '@/api/client'
import {
  getTelegramWebApp,
  resolveTelegramInitData,
  waitForTelegramInitData,
} from '@/tg-mini/lib/telegramInitData'
import type {
  AdminNotifySettings,
  FeatureModulesResponse,
  InstallPlatform,
  SelfServiceQuota,
  TelegramSettings,
  TgMiniAuthResponse,
  TgMiniConfig,
  TgMiniConfigFile,
  TgMiniDashboard,
  TgMiniNodeActionResponse,
  TgMiniNodesResponse,
  TgMiniQrLink,
  TgMiniSettings,
  TgMiniWarperStatus,
  TgMiniCidrStatus,
  User,
  VpnConfig,
  VpnType,
  ClientTemplate,
  ClientAccessPolicy,
} from '@/types'

const API_BASE = '/api/tg-mini'
const PANEL_API_BASE = '/api'
const TOKEN_KEY = 'tg_token'

export function getTgToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setTgToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearTgToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

async function parseApiResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = 'Ошибка запроса'
    const body = await response.text()
    if (body) {
      try {
        const data = JSON.parse(body) as { detail?: unknown }
        if (data.detail != null) {
          detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
        } else {
          detail = body
        }
      } catch {
        detail = body
      }
    }
    throw new ApiError(detail, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

async function tgFetch<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getTgToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (response.status === 401 && retry && path !== '/auth') {
    const refreshed = await refreshTgSession()
    if (refreshed) {
      return tgFetch<T>(path, options, false)
    }
    clearTgToken()
  }
  return parseApiResponse<T>(response)
}

async function panelApiFetch<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getTgToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(`${PANEL_API_BASE}${path}`, { ...options, headers })
  if (response.status === 401 && retry) {
    const refreshed = await refreshTgSession()
    if (refreshed) {
      return panelApiFetch<T>(path, options, false)
    }
    clearTgToken()
  }
  return parseApiResponse<T>(response)
}

export async function refreshTgSessionFromInitData(initData: string): Promise<void> {
  clearTgToken()
  const auth = await tgAuth(initData)
  setTgToken(auth.access_token)
}

/** Re-issue JWT from Telegram initData (after 401 or on cold start). */
export async function refreshTgSession(): Promise<boolean> {
  const tg = getTelegramWebApp()
  let initData = resolveTelegramInitData(tg)
  if (!initData) {
    initData = await waitForTelegramInitData(tg)
  }
  if (!initData) return false
  await refreshTgSessionFromInitData(initData)
  return true
}

export async function tgAuth(initData: string): Promise<TgMiniAuthResponse> {
  const response = await fetch(`${API_BASE}/auth`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ init_data: initData }),
  })
  return parseApiResponse<TgMiniAuthResponse>(response)
}

export async function getTgDashboard(): Promise<TgMiniDashboard> {
  return tgFetch<TgMiniDashboard>('/dashboard')
}

export async function getTgConfigs(): Promise<{ configs: TgMiniConfig[] }> {
  return tgFetch<{ configs: TgMiniConfig[] }>('/configs')
}

export async function getTgConfigFiles(configId: number): Promise<{ files: TgMiniConfigFile[] }> {
  return tgFetch<{ files: TgMiniConfigFile[] }>(`/configs/${configId}/files`)
}

export async function sendTgConfig(
  configId: number,
  data: { path?: string; destination: 'self' | 'owner'; platform?: InstallPlatform },
): Promise<{ message: string }> {
  return tgFetch<{ message: string }>(`/configs/${configId}/send`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getTgQrLink(configId: number, path: string): Promise<TgMiniQrLink> {
  const params = new URLSearchParams({ config_id: String(configId), path })
  return tgFetch<TgMiniQrLink>(`/qr-link?${params.toString()}`)
}

export async function getTgSettings(): Promise<TgMiniSettings> {
  return tgFetch<TgMiniSettings>('/settings')
}

export async function getTgAdminNotify(): Promise<AdminNotifySettings> {
  return tgFetch<AdminNotifySettings>('/admin-notify')
}

export async function updateTgAdminNotify(data: {
  telegram_id?: string
  events?: Record<string, boolean>
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
}): Promise<TelegramSettings> {
  return tgFetch<TelegramSettings>('/telegram-settings', {
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

export async function getTgWarperStatus(): Promise<TgMiniWarperStatus> {
  return tgFetch<TgMiniWarperStatus>('/warper/status')
}

export async function getTgCidrStatus(): Promise<TgMiniCidrStatus> {
  return tgFetch<TgMiniCidrStatus>('/cidr/status')
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
  const data = await panelApiFetch<
    Record<string, { openvpn: ClientAccessPolicy; wireguard: ClientAccessPolicy }>
  >(`/client-access/policies?${params.toString()}`)
  const entry = data[clientName]
  if (!entry) return null
  return vpnType === 'openvpn' ? entry.openvpn : entry.wireguard
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
