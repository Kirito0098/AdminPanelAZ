// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FeatureModulesProvider, useFeatureModules } from '@/context/FeatureModulesContext'

const auth = vi.hoisted(() => ({ user: null as { username: string } | null }))
const getFeatureModules = vi.hoisted(() => vi.fn())

vi.mock('@/context/AuthContext', () => ({ useAuth: () => auth }))
vi.mock('@/api/client', () => ({ getFeatureModules }))

function Probe() {
  const { isEnabled, loading } = useFeatureModules()
  return <span>{loading ? 'loading' : `telegram:${isEnabled('telegram')}`}</span>
}

describe('FeatureModulesProvider', () => {
  afterEach(cleanup)

  beforeEach(() => {
    auth.user = null
    getFeatureModules.mockReset()
    getFeatureModules.mockResolvedValue({ features: { telegram: false }, frontend_paths: {}, settings_tabs: {} })
  })

  it('does not request modules before login', async () => {
    render(
      <FeatureModulesProvider>
        <Probe />
      </FeatureModulesProvider>,
    )
    await screen.findByText('telegram:true')
    expect(getFeatureModules).not.toHaveBeenCalled()
  })

  it('loads modules once the user is logged in', async () => {
    const { rerender } = render(
      <FeatureModulesProvider>
        <Probe />
      </FeatureModulesProvider>,
    )
    auth.user = { username: 'admin' }
    await act(async () => {
      rerender(
        <FeatureModulesProvider>
          <Probe />
        </FeatureModulesProvider>,
      )
    })
    await waitFor(() => expect(screen.getByText('telegram:false')).toBeTruthy())
    expect(getFeatureModules).toHaveBeenCalledTimes(1)
  })
})
