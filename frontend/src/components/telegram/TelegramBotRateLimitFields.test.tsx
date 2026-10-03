// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { notify } from '@/test/nodePageHarness'
import type { TelegramSettings } from '@/types'
import TelegramBotRateLimitFields from './TelegramBotRateLimitFields'

const api = vi.hoisted(() => ({ updateTelegramSettings: vi.fn() }))

vi.mock('@/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/client')>()),
  ...api,
}))
vi.mock('@/context/NotificationContext', async () => (await import('@/test/nodePageHarness')).notificationModule)

function settings(overrides: Partial<TelegramSettings> = {}): TelegramSettings {
  return {
    bot_command_rate_max: 30,
    bot_command_rate_window_seconds: 60,
    bot_command_rate_limit_enabled: true,
    ...overrides,
  } as TelegramSettings
}

describe('TelegramBotRateLimitFields', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('saves max and window in seconds', async () => {
    const onSaved = vi.fn()
    api.updateTelegramSettings.mockResolvedValue(settings({ bot_command_rate_max: 10 }))
    render(<TelegramBotRateLimitFields settings={settings()} onSaved={onSaved} />)
    fireEvent.change(screen.getByLabelText('Команд за окно'), { target: { value: '10' } })
    fireEvent.change(screen.getByLabelText('Окно, секунд'), { target: { value: '120' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить лимит' }))
    await waitFor(() =>
      expect(api.updateTelegramSettings).toHaveBeenCalledWith({
        bot_command_rate_max: 10,
        bot_command_rate_window_seconds: 120,
      }),
    )
    expect(onSaved).toHaveBeenCalled()
  })

  it('rejects window outside 10–3600 seconds', () => {
    render(<TelegramBotRateLimitFields settings={settings()} onSaved={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Окно, секунд'), { target: { value: '5' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить лимит' }))
    expect(notify.error).toHaveBeenCalled()
    expect(api.updateTelegramSettings).not.toHaveBeenCalled()
  })

  it('warns when the limit is disabled by server config', () => {
    render(
      <TelegramBotRateLimitFields settings={settings({ bot_command_rate_limit_enabled: false })} onSaved={vi.fn()} />,
    )
    expect(screen.getByText(/TELEGRAM_BOT_COMMAND_RATE_LIMIT_ENABLED/)).toBeTruthy()
  })
})
