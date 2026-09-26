import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const initData = vi.hoisted(() => ({ value: 'init-data' as string | null }))

vi.mock('@/tg-mini/lib/telegramInitData', () => ({
  getTelegramWebApp: () => ({}),
  resolveTelegramInitData: () => initData.value,
  waitForTelegramInitData: async () => initData.value,
}))

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function authHeader(call: unknown[]): string | null {
  return new Headers((call[1] as RequestInit | undefined)?.headers).get('Authorization')
}

async function loadApi() {
  vi.resetModules()
  return import('./api')
}

describe('Mini App token storage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('keeps the token in memory and drops the legacy localStorage copy', async () => {
    const storage = { getItem: vi.fn(() => 'legacy'), setItem: vi.fn(), removeItem: vi.fn() }
    vi.stubGlobal('localStorage', storage)

    const api = await loadApi()
    expect(storage.removeItem).toHaveBeenCalledWith('tg_token')
    expect(api.getTgToken()).toBeNull()

    api.setTgToken('t1')
    expect(api.getTgToken()).toBe('t1')
    api.clearTgToken()
    expect(api.getTgToken()).toBeNull()
    expect(storage.setItem).not.toHaveBeenCalled()
    expect(storage.getItem).not.toHaveBeenCalled()
  })

  it('works where localStorage is unavailable', async () => {
    vi.stubGlobal('localStorage', {
      removeItem: () => {
        throw new Error('SecurityError')
      },
    })

    const api = await loadApi()
    api.setTgToken('t1')
    expect(api.getTgToken()).toBe('t1')
  })
})

describe('Mini App session refresh', () => {
  let api: Awaited<ReturnType<typeof loadApi>>

  beforeEach(async () => {
    initData.value = 'init-data'
    api = await loadApi()
    api.setTgToken('old')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('clears the token when Telegram gives no initData to renew with', async () => {
    initData.value = null
    const fetchMock = vi.fn(async () => json(401, { detail: 'expired' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.getTgDashboard()).rejects.toMatchObject({ status: 401 })
    expect(api.getTgToken()).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('renews the token once for parallel 401s and retries each request', async () => {
    let releaseAuth!: () => void
    const authGate = new Promise<void>((resolve) => {
      releaseAuth = resolve
    })
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/tg-mini/auth')) {
        await authGate
        return json(200, { access_token: 'new' })
      }
      const auth = new Headers(init?.headers).get('Authorization')
      return auth === 'Bearer new' ? json(200, { ok: url }) : json(401, { detail: 'expired' })
    })
    vi.stubGlobal('fetch', fetchMock)

    const pending = Promise.all([api.getTgDashboard(), api.getTgConfigs(), api.getTgFeatureModules()])
    await vi.waitFor(() => expect(fetchMock.mock.calls.filter((c) => String(c[0]).endsWith('/auth'))).toHaveLength(1))
    releaseAuth()
    const results = await pending

    expect(results).toHaveLength(3)
    expect(fetchMock.mock.calls.filter((c) => String(c[0]).endsWith('/tg-mini/auth'))).toHaveLength(1)
    expect(api.getTgToken()).toBe('new')
  })

  it('does not drop the old token while the renewal is in flight', async () => {
    let releaseAuth!: () => void
    const authGate = new Promise<void>((resolve) => {
      releaseAuth = resolve
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.endsWith('/tg-mini/auth')) {
          await authGate
          return json(200, { access_token: 'new' })
        }
        return json(401, { detail: 'expired' })
      }),
    )

    const renewal = api.refreshTgSession()
    await Promise.resolve()
    expect(api.getTgToken()).toBe('old')
    releaseAuth()
    await expect(renewal).resolves.toBe(true)
    expect(api.getTgToken()).toBe('new')
  })

  it('retries without a new /auth when another request already renewed the token', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/tg-mini/auth')) return json(200, { access_token: 'unexpected' })
      const auth = new Headers(init?.headers).get('Authorization')
      if (auth === 'Bearer old') {
        api.setTgToken('renewed')
        return json(401, { detail: 'expired' })
      }
      return json(200, { ok: true })
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.getTgDashboard()).resolves.toEqual({ ok: true })

    expect(fetchMock.mock.calls.map(authHeader)).toEqual(['Bearer old', 'Bearer renewed'])
  })

  it('clears the token when the renewal is refused', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        url.endsWith('/tg-mini/auth')
          ? json(401, { detail: 'TG ID не привязан' })
          : json(401, { detail: 'expired' }),
      ),
    )

    await expect(api.getTgDashboard()).rejects.toMatchObject({ status: 401 })
    expect(api.getTgToken()).toBeNull()
  })

  it('starts a fresh renewal after the previous one finished', async () => {
    const fetchMock = vi.fn(async (url: string) =>
      url.endsWith('/tg-mini/auth') ? json(200, { access_token: `t${fetchMock.mock.calls.length}` }) : json(200, {}),
    )
    vi.stubGlobal('fetch', fetchMock)

    await api.refreshTgSession()
    await api.refreshTgSession()

    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
