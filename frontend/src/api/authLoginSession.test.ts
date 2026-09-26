import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { login, login2FA, loginWithCaptcha, verifyPasskeyLogin } from './auth'
import * as webSession from '@/lib/webSession'

function respond(body: unknown) {
  const fetchMock = vi.fn(
    async (_url: string, _init?: RequestInit) =>
      new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('login calls remember the web session so it can be revoked', () => {
  let stored: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    vi.spyOn(webSession, 'getWebSessionId').mockReturnValue(null)
    stored = vi.spyOn(webSession, 'storeWebSessionId').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it.each([
    ['password', () => login('alice', 'pw')],
    ['captcha', () => loginWithCaptcha('alice', 'pw', 'cid', 'ABCD')],
    ['2FA', () => login2FA('temp', '123456')],
    ['passkey', () => verifyPasskeyLogin('temp', 'key', { id: 'c' })],
  ])('%s login stores the session id', async (_name, call) => {
    respond({ access_token: 't', web_session_id: 'ws-1' })

    await expect(call()).resolves.toMatchObject({ access_token: 't' })

    expect(stored).toHaveBeenCalledWith('ws-1')
  })

  it('sends the captcha answer', async () => {
    const fetchMock = respond({ access_token: 't', web_session_id: 'ws-1' })

    await loginWithCaptcha('alice', 'pw', 'cid', 'ABCD')

    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      username: 'alice',
      password: 'pw',
      captcha_id: 'cid',
      captcha_text: 'ABCD',
    })
  })

  it('stores nothing while the second factor is pending or when no id is returned', async () => {
    respond({ requires_2fa: true, temp_token: 'temp' })
    await login('alice', 'pw')
    respond({ access_token: 't' })
    await loginWithCaptcha('alice', 'pw', 'cid', 'ABCD')

    expect(stored).not.toHaveBeenCalled()
  })
})
