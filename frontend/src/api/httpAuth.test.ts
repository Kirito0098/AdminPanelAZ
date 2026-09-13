import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  apiFetchAtBase,
  isNodeAgentAuthFailureDetail,
  refreshAccessToken,
} from './http'
import * as accessToken from '@/lib/accessToken'
import * as webSession from '@/lib/webSession'

describe('isNodeAgentAuthFailureDetail', () => {
  it('detects Russian key message and X-Node-Key', () => {
    expect(isNodeAgentAuthFailureDetail('Неверный API-ключ узла (заголовок X-Node-Key)')).toBe(true)
    expect(isNodeAgentAuthFailureDetail('X-Node-Key rejected')).toBe(true)
  })

  it('detects structured node_auth code', () => {
    expect(isNodeAgentAuthFailureDetail({ code: 'node_auth', message: 'bad key' })).toBe(true)
  })

  it('ignores ordinary session messages', () => {
    expect(isNodeAgentAuthFailureDetail('Not authenticated')).toBe(false)
    expect(isNodeAgentAuthFailureDetail('Неверный токен авторизации')).toBe(false)
    expect(isNodeAgentAuthFailureDetail(undefined)).toBe(false)
  })
})

describe('refreshAccessToken mutex', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('dedupes concurrent refresh into one fetch', async () => {
    let resolves!: (v: Response) => void
    const fetchMock = vi.fn(
      () =>
        new Promise<Response>((r) => {
          resolves = r
        }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const p1 = refreshAccessToken()
    const p2 = refreshAccessToken()
    expect(fetchMock).toHaveBeenCalledTimes(1)

    resolves(
      new Response(JSON.stringify({ access_token: 't1' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    await expect(Promise.all([p1, p2])).resolves.toEqual(['t1', 't1'])
  })
})

describe('apiFetchAtBase session vs node-key auth', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('does not clear access token or call refresh on node-key 401', async () => {
    const clearSpy = vi.spyOn(accessToken, 'clearAccessToken')
    vi.spyOn(accessToken, 'getAccessToken').mockReturnValue('valid-jwt')
    vi.spyOn(webSession, 'getWebSessionId').mockReturnValue(null)
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Неверный API-ключ узла (заголовок X-Node-Key)' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiFetchAtBase('/api', '/configs', {}, true)).rejects.toMatchObject({
      status: 401,
    })
    expect(clearSpy).not.toHaveBeenCalled()
    // Only the original request — no /auth/refresh
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('on session 401 calls /auth/refresh once then retries the request', async () => {
    vi.spyOn(accessToken, 'getAccessToken').mockReturnValue('old-jwt')
    vi.spyOn(accessToken, 'setAccessToken')
    vi.spyOn(webSession, 'getWebSessionId').mockReturnValue(null)

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'Неверный токен авторизации' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ access_token: 'new-jwt' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiFetchAtBase('/api', '/configs', {}, true)).resolves.toEqual({ ok: true })

    const refreshCalls = fetchMock.mock.calls.filter((call) =>
      String(call[0]).includes('/auth/refresh'),
    )
    expect(refreshCalls).toHaveLength(1)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('502 with node-key detail does not trigger session refresh (Mikhail path)', async () => {
    const clearSpy = vi.spyOn(accessToken, 'clearAccessToken')
    vi.spyOn(accessToken, 'getAccessToken').mockReturnValue('valid-jwt')
    vi.spyOn(webSession, 'getWebSessionId').mockReturnValue(null)
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Неверный API-ключ узла (заголовок X-Node-Key)' }), {
        status: 502,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiFetchAtBase('/api', '/monitoring/overview', {}, true)).rejects.toMatchObject({
      status: 502,
    })
    expect(clearSpy).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls.some((call) => String(call[0]).includes('/auth/refresh'))).toBe(
      false,
    )
  })
})
