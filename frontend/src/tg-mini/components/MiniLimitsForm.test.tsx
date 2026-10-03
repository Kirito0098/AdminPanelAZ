// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { TelegramSettings } from '@/types'
import MiniLimitsForm from './MiniLimitsForm'

const api = vi.hoisted(() => ({
  getTgSelfServiceLimits: vi.fn(),
  updateTgSelfServiceLimits: vi.fn(),
  updateTgTelegramSettings: vi.fn(),
}))

vi.mock('@/tg-mini/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/tg-mini/api')>()),
  ...api,
}))

const LIMITS = { quota_default: 5, create_rate_max: 3, create_rate_window_seconds: 3600 }
const TELEGRAM = {
  bot_command_rate_max: 30,
  bot_command_rate_window_seconds: 60,
  bot_command_rate_limit_enabled: true,
} as TelegramSettings

describe('MiniLimitsForm', () => {
  beforeEach(() => {
    api.getTgSelfServiceLimits.mockResolvedValue(LIMITS)
    api.updateTgSelfServiceLimits.mockImplementation(async (data) => ({ ...LIMITS, ...data }))
    api.updateTgTelegramSettings.mockImplementation(async (data) => ({ ...TELEGRAM, ...data }))
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('saves self-service and bot limits together', async () => {
    const onTelegramSaved = vi.fn()
    const onFeedback = vi.fn()
    render(<MiniLimitsForm telegram={TELEGRAM} onTelegramSaved={onTelegramSaved} onFeedback={onFeedback} />)
    const quota = await screen.findByLabelText('Квота по умолчанию')
    fireEvent.change(quota, { target: { value: '8' } })
    fireEvent.change(screen.getByLabelText('Окно создания, мин'), { target: { value: '30' } })
    fireEvent.change(screen.getByLabelText('Команд бота за окно'), { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить лимиты' }))
    await waitFor(() =>
      expect(api.updateTgSelfServiceLimits).toHaveBeenCalledWith({
        quota_default: 8,
        create_rate_max: 3,
        create_rate_window_seconds: 1800,
      }),
    )
    expect(api.updateTgTelegramSettings).toHaveBeenCalledWith({
      bot_command_rate_max: 0,
      bot_command_rate_window_seconds: 60,
    })
    await waitFor(() => expect(onTelegramSaved).toHaveBeenCalled())
    expect(onFeedback).toHaveBeenLastCalledWith({ tone: 'success', text: 'Лимиты сохранены' })
  })

  it('reports invalid input without saving', async () => {
    const onFeedback = vi.fn()
    render(<MiniLimitsForm telegram={TELEGRAM} onTelegramSaved={vi.fn()} onFeedback={onFeedback} />)
    const quota = await screen.findByLabelText('Квота по умолчанию')
    fireEvent.change(quota, { target: { value: 'abc' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить лимиты' }))
    expect(onFeedback).toHaveBeenCalledWith(expect.objectContaining({ tone: 'error' }))
    expect(api.updateTgSelfServiceLimits).not.toHaveBeenCalled()
    expect(api.updateTgTelegramSettings).not.toHaveBeenCalled()
  })
})
