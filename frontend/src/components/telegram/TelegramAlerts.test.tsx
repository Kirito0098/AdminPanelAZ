// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'

import type { TelegramSettings } from '@/types'
import TelegramAlerts from './TelegramAlerts'
import type { TelegramSettingsHook } from './useTelegramSettings'

type HookOverrides = Omit<Partial<TelegramSettingsHook>, 'settings'> & { settings?: Partial<TelegramSettings> }

function makeHook({ settings: settingsOverrides, ...overrides }: HookOverrides = {}): TelegramSettingsHook {
  const settings = {
    bot_token_set: true,
    interactive_enabled: true,
    relay_node_ids: [],
    relay_last_error: '',
    relay_last_ok_at: '',
    ...settingsOverrides,
  } as unknown as TelegramSettings
  return {
    loading: false,
    settings,
    interactiveEnabled: true,
    webhookReady: false,
    relayEnabled: false,
    relayError: '',
    commandsConnected: false,
    commandsReady: false,
    notifyOnBackup: false,
    hasBackupRecipients: true,
    notifyEnabled: true,
    hasNotifyRecipients: true,
    notifyEventsEnabled: 1,
    ...overrides,
  } as unknown as TelegramSettingsHook
}

function renderAlerts(tg: TelegramSettingsHook) {
  return render(
    <MemoryRouter>
      <TelegramAlerts tg={tg} />
    </MemoryRouter>,
  )
}

describe('TelegramAlerts: подключение команд бота', () => {
  afterEach(() => {
    cleanup()
  })

  it('не ругается, когда команды идут через узел вместо webhook', () => {
    renderAlerts(
      makeHook({
        relayEnabled: true,
        commandsConnected: true,
        commandsReady: true,
        settings: { relay_node_ids: [1], relay_last_ok_at: '2026-10-22T10:00:00+00:00', relay_last_node: 'nl-1' },
      }),
    )

    expect(screen.queryByText('Команды бота не подключены')).toBeNull()
    expect(screen.queryByText('Связь с Telegram через узел не работает')).toBeNull()
  })

  it('предупреждает, когда нет ни webhook, ни узла', () => {
    renderAlerts(makeHook())

    expect(screen.queryByText('Команды бота не подключены')).not.toBeNull()
  })

  it('не предупреждает при зарегистрированном webhook', () => {
    renderAlerts(makeHook({ webhookReady: true, commandsConnected: true, commandsReady: true }))

    expect(screen.queryByText('Команды бота не подключены')).toBeNull()
  })

  it('показывает ошибку узла вместо предложения подключить webhook', () => {
    renderAlerts(
      makeHook({
        relayEnabled: true,
        relayError: 'Узел nl-1 не отвечает',
        commandsConnected: true,
        settings: { relay_node_ids: [1], relay_last_error: 'Узел nl-1 не отвечает' },
      }),
    )

    expect(screen.queryByText('Связь с Telegram через узел не работает')).not.toBeNull()
    expect(screen.queryByText('Команды бота не подключены')).toBeNull()
  })
})
