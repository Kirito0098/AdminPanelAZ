import { ApiError } from '@/api/client'
import type {
  AdminNotifySettings,
  TelegramSettings,
  TgMiniAuthResponse,
  TgMiniConfig,
  TgMiniConfigFile,
  TgMiniDashboard,
  TgMiniNodeActionResponse,
  TgMiniNodesResponse,
  TgMiniQrLink,
  TgMiniSettings,
} from '@/types'

const API_BASE = '/api/tg-mini'
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

async function tgFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getTgToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
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

export async function tgAuth(initData: string): Promise<TgMiniAuthResponse> {
  return tgFetch<TgMiniAuthResponse>('/auth', {
    method: 'POST',
    body: JSON.stringify({ init_data: initData }),
  })
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
  data: { path?: string; destination: 'self' | 'chat' },
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
