import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  CHUNK_RELOAD_STORAGE_KEY,
  installPreloadErrorReload,
  isChunkLoadError,
  reloadOnChunkError,
  retryImport,
  shouldAutoReload,
} from './lazyWithRetry'

function memoryStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial))
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => {
      data.set(key, value)
    },
  }
}

const chunkError = () => new TypeError('Failed to fetch dynamically imported module: https://panel/assets/TrafficPage-abc.js')

describe('isChunkLoadError', () => {
  it.each([
    'Failed to fetch dynamically imported module: https://panel/assets/DashboardPage-1.js',
    'Importing a module script failed.',
    'error loading dynamically imported module: https://panel/assets/LogsPage-2.js',
  ])('recognizes %s', (message) => {
    expect(isChunkLoadError(new TypeError(message))).toBe(true)
  })

  it('recognizes ChunkLoadError by name', () => {
    const err = new Error('Loading chunk 7 failed.')
    err.name = 'ChunkLoadError'
    expect(isChunkLoadError(err)).toBe(true)
  })

  it.each([new Error('boom'), new TypeError("Cannot read properties of undefined (reading 'map')"), null, undefined, 'Failed'])(
    'ignores %s',
    (value) => {
      expect(isChunkLoadError(value)).toBe(false)
    },
  )
})

describe('retryImport', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('retries after 500 ms and 1500 ms, then resolves', async () => {
    const mod = { default: () => null }
    const factory = vi
      .fn<() => Promise<typeof mod>>()
      .mockRejectedValueOnce(chunkError())
      .mockRejectedValueOnce(chunkError())
      .mockResolvedValueOnce(mod)

    const result = retryImport(factory)
    await vi.advanceTimersByTimeAsync(0)
    expect(factory).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(499)
    expect(factory).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(factory).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(1499)
    expect(factory).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(1)
    expect(factory).toHaveBeenCalledTimes(3)

    await expect(result).resolves.toBe(mod)
  })

  it('rejects with the last error after 3 attempts in total', async () => {
    const last = chunkError()
    const factory = vi
      .fn<() => Promise<unknown>>()
      .mockRejectedValueOnce(chunkError())
      .mockRejectedValueOnce(chunkError())
      .mockRejectedValueOnce(last)

    const result = retryImport(factory)
    const assertion = expect(result).rejects.toBe(last)
    await vi.advanceTimersByTimeAsync(2000)

    await assertion
    expect(factory).toHaveBeenCalledTimes(3)
  })

  it('does not retry a successful import', async () => {
    const factory = vi.fn(() => Promise.resolve({ default: 1 }))

    await expect(retryImport(factory)).resolves.toEqual({ default: 1 })
    expect(factory).toHaveBeenCalledTimes(1)
  })
})

describe('shouldAutoReload', () => {
  it('allows the first reload and stores the timestamp', () => {
    const storage = memoryStorage()

    expect(shouldAutoReload(storage, 1_000_000)).toBe(true)
    expect(storage.getItem(CHUNK_RELOAD_STORAGE_KEY)).toBe('1000000')
  })

  it('blocks a second reload within 60 s', () => {
    const storage = memoryStorage()

    expect(shouldAutoReload(storage, 1_000_000)).toBe(true)
    expect(shouldAutoReload(storage, 1_059_999)).toBe(false)
  })

  it('ignores a flag older than 60 s', () => {
    const storage = memoryStorage({ [CHUNK_RELOAD_STORAGE_KEY]: '1000000' })

    expect(shouldAutoReload(storage, 1_060_000)).toBe(true)
    expect(storage.getItem(CHUNK_RELOAD_STORAGE_KEY)).toBe('1060000')
  })

  it('ignores a garbage flag', () => {
    expect(shouldAutoReload(memoryStorage({ [CHUNK_RELOAD_STORAGE_KEY]: 'nope' }), 1_000_000)).toBe(true)
  })

  it('does not reload when sessionStorage is unavailable', () => {
    const storage = {
      getItem: () => {
        throw new Error('SecurityError')
      },
      setItem: () => {
        throw new Error('SecurityError')
      },
    }

    expect(shouldAutoReload(storage, 1_000_000)).toBe(false)
  })
})

describe('reloadOnChunkError', () => {
  let storage: ReturnType<typeof memoryStorage>
  let reload: ReturnType<typeof vi.fn>

  beforeEach(() => {
    storage = memoryStorage()
    reload = vi.fn()
    vi.stubGlobal('window', { sessionStorage: storage, location: { reload } })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reloads once, not twice within 60 s (window.location.reload)', () => {
    expect(reloadOnChunkError(chunkError(), { now: 1_000_000 })).toBe(true)
    expect(reloadOnChunkError(chunkError(), { now: 1_030_000 })).toBe(false)

    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('reloads again after the 60 s window', () => {
    reloadOnChunkError(chunkError(), { now: 1_000_000 })
    reloadOnChunkError(chunkError(), { now: 1_060_001 })

    expect(reload).toHaveBeenCalledTimes(2)
  })

  it('does not reload for ordinary render errors', () => {
    expect(reloadOnChunkError(new Error('boom'), { now: 1_000_000 })).toBe(false)

    expect(reload).not.toHaveBeenCalled()
    expect(storage.getItem(CHUNK_RELOAD_STORAGE_KEY)).toBeNull()
  })
})

describe('installPreloadErrorReload', () => {
  function preloadError(payload: Error) {
    const event = new Event('vite:preloadError', { cancelable: true }) as Event & { payload: Error }
    event.payload = payload
    return event
  }

  it('takes over with a guarded reload and prevents the default throw', () => {
    const target = new EventTarget()
    const storage = memoryStorage()
    const reload = vi.fn()
    installPreloadErrorReload(target, { storage, reload, now: () => 1_000_000 })

    const first = preloadError(chunkError())
    target.dispatchEvent(first)
    expect(reload).toHaveBeenCalledTimes(1)
    expect(first.defaultPrevented).toBe(true)

    const second = preloadError(chunkError())
    target.dispatchEvent(second)
    expect(reload).toHaveBeenCalledTimes(1)
    expect(second.defaultPrevented).toBe(false)
  })

  it('handles CSS preload failures too', () => {
    const target = new EventTarget()
    const reload = vi.fn()
    installPreloadErrorReload(target, { storage: memoryStorage(), reload, now: () => 1_000_000 })

    const event = preloadError(new Error('Unable to preload CSS for https://panel/assets/LogsPage-3.css'))
    target.dispatchEvent(event)

    expect(reload).toHaveBeenCalledTimes(1)
    expect(event.defaultPrevented).toBe(true)
  })

  it('leaves failures of non-final retry attempts to retryImport', async () => {
    vi.useFakeTimers()
    try {
      const target = new EventTarget()
      const reload = vi.fn()
      installPreloadErrorReload(target, { storage: memoryStorage(), reload, now: () => 1_000_000 })

      const events: Event[] = []
      const factory = vi.fn(() => {
        const event = preloadError(chunkError())
        events.push(event)
        target.dispatchEvent(event)
        return Promise.reject(event.payload)
      })

      const result = retryImport(factory)
      const assertion = expect(result).rejects.toThrow('Failed to fetch dynamically imported module')
      await vi.advanceTimersByTimeAsync(2000)
      await assertion

      expect(events.map((e) => e.defaultPrevented)).toEqual([false, false, true])
      expect(reload).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('registers the listener only once per target', () => {
    const target = new EventTarget()
    const first = vi.fn()
    const second = vi.fn()
    installPreloadErrorReload(target, { storage: memoryStorage(), reload: first, now: () => 1_000_000 })
    installPreloadErrorReload(target, { storage: memoryStorage(), reload: second, now: () => 1_000_000 })

    target.dispatchEvent(preloadError(chunkError()))

    expect(first).toHaveBeenCalledTimes(1)
    expect(second).not.toHaveBeenCalled()
  })
})
