import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type Tab = typeof import('./http')

/** Each import after resetModules is a separate tab with its own in-tab single-flight. */
async function openTab(): Promise<Tab> {
  vi.resetModules()
  return import('./http')
}

/** FIFO exclusive locks shared by every "tab" of the test, like one browser origin. */
function createLockManager() {
  const tails = new Map<string, Promise<unknown>>()
  const manager = {
    held: new Set<string>(),
    request: vi.fn(<T>(name: string, callback: (lock: unknown) => Promise<T>): Promise<T> => {
      const run = (tails.get(name) ?? Promise.resolve()).then(async () => {
        manager.held.add(name)
        try {
          return await callback({ name, mode: 'exclusive' })
        } finally {
          manager.held.delete(name)
        }
      })
      tails.set(
        name,
        run.catch(() => undefined),
      )
      return run
    }),
  }
  return manager
}

function tokenResponse(token: string): Response {
  return new Response(JSON.stringify({ access_token: token }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function deferredFetch() {
  const pending: Array<{ resolve: (r: Response) => void; reject: (e: unknown) => void }> = []
  const fetchMock = vi.fn(
    (_url: string, init?: RequestInit) =>
      new Promise<Response>((resolve, reject) => {
        pending.push({ resolve, reject })
        init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
      }),
  )
  return { fetchMock, pending }
}

async function flush(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await Promise.resolve()
}

describe('refreshAccessToken is serialized across tabs', () => {
  let locks: ReturnType<typeof createLockManager>

  beforeEach(() => {
    locks = createLockManager()
    vi.stubGlobal('navigator', { locks })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('does not start a second tab refresh until the first one answered', async () => {
    const { fetchMock, pending } = deferredFetch()
    vi.stubGlobal('fetch', fetchMock)
    const tabA = await openTab()
    const tabB = await openTab()

    const first = tabA.refreshAccessToken()
    const second = tabB.refreshAccessToken()
    await flush()

    expect(locks.request).toHaveBeenCalledTimes(2)
    expect(locks.request.mock.calls.map((call) => call[0])).toEqual(['az-auth-refresh', 'az-auth-refresh'])
    expect(fetchMock).toHaveBeenCalledTimes(1)

    pending[0].resolve(tokenResponse('t1'))
    await expect(first).resolves.toBe('t1')
    await flush()
    expect(fetchMock).toHaveBeenCalledTimes(2)

    pending[1].resolve(tokenResponse('t2'))
    await expect(second).resolves.toBe('t2')
    expect(locks.held.size).toBe(0)
  })

  it('keeps one refresh per tab while the lock is awaited', async () => {
    const { fetchMock, pending } = deferredFetch()
    vi.stubGlobal('fetch', fetchMock)
    const tab = await openTab()

    const calls = [tab.refreshAccessToken(), tab.refreshAccessToken()]
    await flush()

    expect(locks.request).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    pending[0].resolve(tokenResponse('t1'))
    await expect(Promise.all(calls)).resolves.toEqual(['t1', 't1'])
  })

  it('releases the lock when the refresh request fails', async () => {
    const { fetchMock, pending } = deferredFetch()
    vi.stubGlobal('fetch', fetchMock)
    const tabA = await openTab()
    const tabB = await openTab()

    const first = tabA.refreshAccessToken()
    const second = tabB.refreshAccessToken()
    await flush()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    pending[0].reject(new TypeError('Failed to fetch'))

    await expect(first).rejects.toMatchObject({ status: 0 })
    await flush()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    pending[1].resolve(tokenResponse('t2'))
    await expect(second).resolves.toBe('t2')
    expect(locks.held.size).toBe(0)
  })

  it('a hung refresh frees the lock after the timeout, and the waiting tab gets a full timeout', async () => {
    vi.useFakeTimers()
    const { fetchMock, pending } = deferredFetch()
    vi.stubGlobal('fetch', fetchMock)
    const tabA = await openTab()
    const tabB = await openTab()

    const first = tabA.refreshAccessToken()
    const firstFailed = expect(first).rejects.toMatchObject({ status: 0 })
    const second = tabB.refreshAccessToken()
    await vi.advanceTimersByTimeAsync(tabA.REFRESH_TIMEOUT_MS)
    await firstFailed

    expect(fetchMock).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(tabA.REFRESH_TIMEOUT_MS - 1)
    pending[1].resolve(tokenResponse('t2'))
    await expect(second).resolves.toBe('t2')
    expect(locks.held.size).toBe(0)
  })
})

describe('refreshAccessToken without Web Locks', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('refreshes directly when navigator.locks is unavailable', async () => {
    vi.stubGlobal('navigator', {})
    const fetchMock = vi.fn(async () => tokenResponse('t1'))
    vi.stubGlobal('fetch', fetchMock)
    const tab = await openTab()

    const pending = tab.refreshAccessToken()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    await expect(pending).resolves.toBe('t1')
  })

  it('refreshes directly when the lock cannot be requested', async () => {
    vi.stubGlobal('navigator', {
      locks: { request: vi.fn().mockRejectedValue(new DOMException('opaque origin', 'SecurityError')) },
    })
    const fetchMock = vi.fn(async () => tokenResponse('t1'))
    vi.stubGlobal('fetch', fetchMock)
    const tab = await openTab()

    await expect(tab.refreshAccessToken()).resolves.toBe('t1')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
