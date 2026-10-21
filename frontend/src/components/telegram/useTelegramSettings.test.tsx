// @vitest-environment jsdom
import { cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AdminNotifySettings, TelegramSettings, User } from '@/types'
import { useTelegramSettings } from './useTelegramSettings'

const api = vi.hoisted(() => ({
  getTelegramSettings: vi.fn(),
  getAdminNotifySettings: vi.fn(),
  getUsers: vi.fn(),
}))

const notify = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))

vi.mock('@/api/client', () => ({
  ApiError: class ApiError extends Error {},
  deleteTelegramWebhook: vi.fn(),
  getAdminNotifySettings: api.getAdminNotifySettings,
  getTelegramLinkCode: vi.fn(),
  getTelegramSettings: api.getTelegramSettings,
  getUsers: api.getUsers,
  registerTelegramWebhook: vi.fn(),
  testAdminNotify: vi.fn(),
  testAdminNotifyEvent: vi.fn(),
  testNocReportPreview: vi.fn(),
  testNocWeeklyImagePreview: vi.fn(),
  testTelegram: vi.fn(),
  updateAdminNotifySettings: vi.fn(),
  updateTelegramSettings: vi.fn(),
  updateUser: vi.fn(),
}))

vi.mock('@/context/NotificationContext', () => ({ useNotifications: () => notify }))

const baseSettings: TelegramSettings = {
  bot_token_set: true,
  bot_username: 'test_bot',
  auth_max_age_seconds: 300,
  mini_app_url: 'https://panel.example/api/tg-mini',
  chat_id: '',
  chat_ids: [],
  notify_enabled: false,
  notify_on_backup: false,
  interactive_enabled: true,
  webhook_registered: false,
  webhook_secret_set: false,
  webhook_set_at: '',
  oidc_enabled: false,
  oidc_client_id: '',
  oidc_client_secret_set: false,
  oidc_callback_url: '',
  oidc_trusted_origin: '',
  legacy_login_enabled: true,
  auth_method: 'legacy',
  login_ready: true,
  bot_command_rate_max: 30,
  bot_command_rate_window_seconds: 60,
  bot_command_rate_limit_enabled: true,
  relay_node_ids: [],
  relay_nodes: [],
  relay_last_ok_at: '',
  relay_last_error: '',
  relay_last_node: '',
  relay_check: [],
  accept_access_requests: false,
  pending_request_cap: 50,
}

const baseNotify: AdminNotifySettings = {
  telegram_id: '',
  recipient_user_ids: [],
  notify_enabled: false,
  bot_token_set: true,
  events: [],
  node_offline_grace_seconds: 180,
}

async function mount(overrides: Partial<TelegramSettings> = {}) {
  api.getTelegramSettings.mockResolvedValue({ ...baseSettings, ...overrides })
  api.getAdminNotifySettings.mockResolvedValue({ ...baseNotify })
  api.getUsers.mockResolvedValue([] as User[])
  const { result } = renderHook(() => useTelegramSettings())
  await waitFor(() => expect(result.current.loading).toBe(false))
  return result
}

describe('useTelegramSettings: признак «команды бота подключены»', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
  })

  it('считает команды подключёнными при связи через узел без webhook', async () => {
    const result = await mount({
      relay_node_ids: [1],
      relay_last_ok_at: '2026-10-22T10:00:00+00:00',
      relay_last_node: 'nl-1',
    })

    expect(result.current.webhookReady).toBe(false)
    expect(result.current.relayEnabled).toBe(true)
    expect(result.current.relayError).toBe('')
    expect(result.current.commandsConnected).toBe(true)
    expect(result.current.commandsReady).toBe(true)
  })

  it('показывает ошибку узла, даже если связь через узел настроена', async () => {
    const result = await mount({
      relay_node_ids: [1],
      relay_last_error: 'Узел nl-1 не отвечает',
    })

    expect(result.current.commandsConnected).toBe(true)
    expect(result.current.relayError).toBe('Узел nl-1 не отвечает')
    expect(result.current.commandsReady).toBe(false)
  })

  it('не считает команды подключёнными без webhook и без узла', async () => {
    const result = await mount()

    expect(result.current.relayEnabled).toBe(false)
    expect(result.current.commandsConnected).toBe(false)
    expect(result.current.commandsReady).toBe(false)
  })

  it('считает команды подключёнными по webhook без узла', async () => {
    const result = await mount({ webhook_registered: true, webhook_set_at: '2026-10-22T10:00:00+00:00' })

    expect(result.current.webhookReady).toBe(true)
    expect(result.current.relayEnabled).toBe(false)
    expect(result.current.commandsConnected).toBe(true)
    expect(result.current.commandsReady).toBe(true)
  })
})
