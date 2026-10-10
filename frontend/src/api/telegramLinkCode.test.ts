import { afterEach, describe, expect, it, vi } from 'vitest'

import { getTelegramLinkCode } from './maintenance'
import * as webSession from '@/lib/webSession'

describe('getTelegramLinkCode', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('posts the current password', async () => {
    vi.spyOn(webSession, 'getWebSessionId').mockReturnValue(null)
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ code: 'abcd1234', expires_in_seconds: 600 }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await getTelegramLinkCode('secret-1')

    expect(result.code).toBe('abcd1234')
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toContain('/telegram/link-code')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({ current_password: 'secret-1' })
  })
})
