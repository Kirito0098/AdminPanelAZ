// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { notify } from '@/test/nodePageHarness'
import SelfServiceLimitsSection from './SelfServiceLimitsSection'

const api = vi.hoisted(() => ({
  getSelfServiceLimits: vi.fn(),
  updateSelfServiceLimits: vi.fn(),
}))

vi.mock('@/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/client')>()),
  ...api,
}))
vi.mock('@/context/NotificationContext', async () => (await import('@/test/nodePageHarness')).notificationModule)

const DEFAULTS = { quota_default: 5, create_rate_max: 3, create_rate_window_seconds: 3600 }

describe('SelfServiceLimitsSection', () => {
  beforeEach(() => {
    api.getSelfServiceLimits.mockResolvedValue(DEFAULTS)
    api.updateSelfServiceLimits.mockImplementation(async (data) => ({ ...DEFAULTS, ...data }))
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('shows loaded limits with the window in minutes', async () => {
    render(<SelfServiceLimitsSection />)
    expect(await screen.findByLabelText('Квота конфигов по умолчанию')).toHaveProperty('value', '5')
    expect(screen.getByLabelText('Созданий за окно')).toHaveProperty('value', '3')
    expect(screen.getByLabelText('Окно, минут')).toHaveProperty('value', '60')
  })

  it('saves limits converting minutes to seconds', async () => {
    render(<SelfServiceLimitsSection />)
    const quota = await screen.findByLabelText('Квота конфигов по умолчанию')
    fireEvent.change(quota, { target: { value: '0' } })
    fireEvent.change(screen.getByLabelText('Окно, минут'), { target: { value: '15' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить лимиты' }))
    await waitFor(() =>
      expect(api.updateSelfServiceLimits).toHaveBeenCalledWith({
        quota_default: 0,
        create_rate_max: 3,
        create_rate_window_seconds: 900,
      }),
    )
    expect(notify.success).toHaveBeenCalled()
  })

  it('rejects out-of-range values without calling the API', async () => {
    render(<SelfServiceLimitsSection />)
    const quota = await screen.findByLabelText('Квота конфигов по умолчанию')
    fireEvent.change(quota, { target: { value: '1001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить лимиты' }))
    expect(notify.error).toHaveBeenCalled()
    expect(api.updateSelfServiceLimits).not.toHaveBeenCalled()
  })
})
