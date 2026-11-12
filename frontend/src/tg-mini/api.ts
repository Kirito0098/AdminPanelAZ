import { apiFetch, apiFetchAtBase, setApiTransport } from '@/api/http'
import {
  getTelegramWebApp,
  resolveTelegramInitData,
  waitForTelegramInitData,
} from '@/tg-mini/lib/telegramInitData'
import type {
  AdminNotifySettings,
  ClosedAccessView,
  InstallPlatform,
  MessageThread,
  SelfServiceLimits,
  SendMessageResult,
  TelegramSettings,
  TgMiniAuthResponse,
  TgMiniConfig,
  TgMiniConfigFile,
  TgMeConfig,
  TgMeStatus,
  TgMiniNodeActionResponse,
  TgMiniNodesResponse,
  TgMiniSettings,
  TgPortalLink,
  UserMessageItem,
  VpnConfig,
} from '@/types'
import { apiBase } from '@/lib/panelBase'

const API_BASE = `${apiBase}/tg-mini`
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

/**
 * The Mini App shares the panel transport and panel API modules, but signs in with a
 * Telegram token: no session cookie, no timezone/session headers, and a 401 is renewed
 * from initData instead of the panel's refresh cookie.
 */
setApiTransport({
  token: () => tgToken,
  onUnauthorized: ({ sentToken }) => renewAfterUnauthorized(sentToken),
})

async function tgFetch<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  return apiFetchAtBase<T>(API_BASE, path, options, retry)
}

function queryString(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value))
  }
  const suffix = search.toString()
  return suffix ? `?${suffix}` : ''
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
  return tgFetch<TgMiniAuthResponse>(
    '/auth',
    { method: 'POST', body: JSON.stringify({ init_data: initData }) },
    false,
  )
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
  return tgFetch<{ index: number; task_id: string }>('/me/plan-configs', {
    method: 'POST',
  })
}

/** Самосервис плана конфигов: убрать имя по индексу. */
export async function removeTgMePlanConfig(
  index: number,
  confirmDeletions = false,
): Promise<{ task_id: string }> {
  const qs = confirmDeletions ? '?confirm_deletions=true' : ''
  return tgFetch<{ task_id: string }>(`/me/plan-configs/${index}${qs}`, {
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

/** Одна панельная конфигурация по id: в `@/api/configs` нет геттера без списка. */
export async function getTgConfig(configId: number): Promise<VpnConfig> {
  return apiFetch<VpnConfig>(`/configs/${configId}?include_files=false`)
}

/* ------------------- Админ: конфиги на активном узле ------------------- */

/** Файлы профиля на активном узле (админский список конфигов). */
export async function getTgAdminConfigFiles(
  configId: number,
): Promise<{ files: TgMiniConfigFile[] }> {
  return tgFetch<{ files: TgMiniConfigFile[] }>(`/configs/${configId}/files`)
}

export async function sendTgAdminConfig(
  configId: number,
  data: { path?: string; destination: 'self' | 'owner'; platform?: InstallPlatform },
): Promise<{ message: string }> {
  return tgFetch<{ message: string }>(`/configs/${configId}/send`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/* ------------------- Чат абонент ↔ администратор ------------------- */

/** Свой диалог абонента (owner scope), новые сообщения первыми. */
export async function getTgMeMessages(
  params: { limit?: number; beforeId?: number } = {},
): Promise<UserMessageItem[]> {
  return tgFetch<UserMessageItem[]>(
    `/me/messages${queryString({ limit: params.limit, before_id: params.beforeId })}`,
  )
}

export async function sendTgMeMessage(text: string): Promise<UserMessageItem> {
  return tgFetch<UserMessageItem>('/me/messages', {
    method: 'POST',
    body: JSON.stringify({ text }),
  })
}

export async function getTgMeMessagesUnread(): Promise<{ count: number }> {
  return tgFetch<{ count: number }>('/me/messages/unread')
}

export async function markTgMeMessagesRead(): Promise<{ marked: number }> {
  return tgFetch<{ marked: number }>('/me/messages/read', { method: 'POST' })
}

/** Админ: список диалогов (поиск по логину, только непрочитанные). */
export async function getTgMessageThreads(
  params: { q?: string; unread?: boolean } = {},
): Promise<MessageThread[]> {
  return tgFetch<MessageThread[]>(
    `/messages/threads${queryString({ q: params.q, unread: params.unread ? 1 : undefined })}`,
  )
}

export async function getTgMessageThread(
  userId: number,
  params: { beforeId?: number; limit?: number } = {},
): Promise<UserMessageItem[]> {
  return tgFetch<UserMessageItem[]>(
    `/messages/${userId}${queryString({ before_id: params.beforeId, limit: params.limit })}`,
  )
}

export async function sendTgMessageThread(userId: number, text: string): Promise<SendMessageResult> {
  return tgFetch<SendMessageResult>(`/messages/${userId}`, {
    method: 'POST',
    body: JSON.stringify({ text }),
  })
}

export async function getTgMessagesUnreadTotal(): Promise<{ count: number }> {
  return tgFetch<{ count: number }>('/messages/unread-count')
}

/** Собственная ссылка клиентского портала: получить, создать, перевыпустить. */
export async function getTgPortalLink(): Promise<TgPortalLink> {
  return tgFetch<TgPortalLink>('/me/portal-link')
}

export async function createTgPortalLink(): Promise<TgPortalLink> {
  return tgFetch<TgPortalLink>('/me/portal-link', { method: 'POST' })
}

export async function rotateTgPortalLink(): Promise<TgPortalLink> {
  return tgFetch<TgPortalLink>('/me/portal-link/rotate', { method: 'POST' })
}

