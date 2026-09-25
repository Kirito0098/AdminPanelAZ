import { afterEach, describe, expect, it, vi } from 'vitest'

import { changePassword } from './auth'
import { getAccessToken, setAccessToken } from '@/lib/accessToken'
import * as webSession from '@/lib/webSession'

describe('changePassword', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    setAccessToken(null)
  })

  it('stores the access token re-issued after the password change', async () => {
    setAccessToken('old-token')
    vi.spyOn(webSession, 'getWebSessionId').mockReturnValue(null)
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({ message: 'ok', access_token: 'new-token' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    await changePassword('old-pass', 'new-pass-123')

    expect(getAccessToken()).toBe('new-token')
  })
})
