import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  REFRESH_TIMEOUT_MS,
  apiFetchAtBase,
  isNodeAgentAuthFailureDetail,
  refreshAccessToken,
} from './http'
import * as accessToken from '@/lib/accessToken'
import { onSessionLost } from '@/lib/sessionLost'
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

describe('refreshAccessToken keeps the session when the server is unavailable', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('clears the session only when the server refuses it', async () => {
    const clearSpy = vi.spyOn(accessToken, 'clearAccessToken')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"expired"}', { status: 401 })))

    await expect(refreshAccessToken()).resolves.toBeNull()
    expect(clearSpy).toHaveBeenCalledTimes(1)
  })

  it.each([500, 502, 503, 504, 408, 429])('throws on %i without clearing the session', async (status) => {
    const clearSpy = vi.spyOn(accessToken, 'clearAccessToken')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>Bad Gateway</html>', { status })))

    await expect(refreshAccessToken()).rejects.toMatchObject({ status })
    expect(clearSpy).not.toHaveBeenCalled()
  })

  it('turns a network error into ApiError(0) without clearing the session', async () => {
    const clearSpy = vi.spyOn(accessToken, 'clearAccessToken')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(refreshAccessToken()).rejects.toMatchObject({ status: 0 })
    expect(clearSpy).not.toHaveBeenCalled()
  })

  it('aborts a refresh the server never answers and frees the shared lock', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn(
      (_url: string, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
        }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const first = refreshAccessToken()
    const assertion = expect(first).rejects.toMatchObject({ status: 0 })
    await vi.advanceTimersByTimeAsync(REFRESH_TIMEOUT_MS)
    await assertion

    fetchMock.mockImplementation(async () =>
      new Response(JSON.stringify({ access_token: 't2' }), { status: 200 }),
    )
    await expect(refreshAccessToken()).resolves.toBe('t2')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('does not leave the abort timer running after an answer', async () => {
    vi.useFakeTimers()
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ access_token: 't3' }), { status: 200 })),
    )

    await expect(refreshAccessToken()).resolves.toBe('t3')
    expect(vi.getTimerCount()).toBe(0)
  })

  it('apiFetch surfaces an unavailable refresh instead of a 401', async () => {
    const clearSpy = vi.spyOn(accessToken, 'clearAccessToken')
    vi.spyOn(accessToken, 'getAccessToken').mockReturnValue('old-jwt')
    vi.spyOn(webSession, 'getWebSessionId').mockReturnValue(null)
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(new Response('{"detail":"Not authenticated"}', { status: 401 }))
        .mockResolvedValueOnce(new Response('', { status: 502 })),
    )

    await expect(apiFetchAtBase('/api', '/configs', {}, true)).rejects.toMatchObject({ status: 502 })
    expect(clearSpy).not.toHaveBeenCalled()
  })
})

describe('final session loss is reported once for every caller', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('reports a refused refresh', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"expired"}', { status: 401 })))
    const listener = vi.fn()
    const unsubscribe = onSessionLost(listener)

    await expect(Promise.all([refreshAccessToken(), refreshAccessToken()])).resolves.toEqual([null, null])
    unsubscribe()

    expect(listener).toHaveBeenCalledTimes(1)
  })

  it('does not report an unavailable server or a successful refresh', async () => {
    const listener = vi.fn()
    const unsubscribe = onSessionLost(listener)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response('', { status: 502 })))
    await expect(refreshAccessToken()).rejects.toMatchObject({ status: 502 })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new TypeError('Failed to fetch')))
    await expect(refreshAccessToken()).rejects.toMatchObject({ status: 0 })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ access_token: 't' }), { status: 200 })),
    )
    await expect(refreshAccessToken()).resolves.toBe('t')
    unsubscribe()

    expect(listener).not.toHaveBeenCalled()
  })

  it('apiFetch reports the loss when the session cannot be renewed', async () => {
    vi.spyOn(accessToken, 'getAccessToken').mockReturnValue('old-jwt')
    vi.spyOn(webSession, 'getWebSessionId').mockReturnValue(null)
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(new Response('{"detail":"Not authenticated"}', { status: 401 }))
        .mockResolvedValueOnce(new Response('{"detail":"expired"}', { status: 401 })),
    )
    const listener = vi.fn()
    const unsubscribe = onSessionLost(listener)

    await expect(apiFetchAtBase('/api', '/configs', {}, true)).rejects.toMatchObject({ status: 401 })
    unsubscribe()

    expect(listener).toHaveBeenCalledTimes(1)
  })

  it('stops notifying after unsubscribe', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 401 })))
    const listener = vi.fn()
    onSessionLost(listener)()

    await refreshAccessToken()

    expect(listener).not.toHaveBeenCalled()
  })
})
