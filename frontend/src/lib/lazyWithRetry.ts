import { lazy } from 'react'

export const CHUNK_RELOAD_STORAGE_KEY = 'az:chunk-reload-at'
const CHUNK_RELOAD_WINDOW_MS = 60_000
const RETRY_DELAYS_MS = [500, 1500]

const CHUNK_ERROR_RE =
  /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module/i

type ReloadStorage = Pick<Storage, 'getItem' | 'setItem'>

type ReloadDeps = {
  storage?: ReloadStorage
  now?: number
  reload?: () => void
}

let nonFinalAttempts = 0

export function isChunkLoadError(error: unknown): boolean {
  if (typeof error !== 'object' || error === null) return false
  const { name, message } = error as { name?: unknown; message?: unknown }
  return name === 'ChunkLoadError' || (typeof message === 'string' && CHUNK_ERROR_RE.test(message))
}

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

async function nonFinalAttempt<T>(factory: () => Promise<T>): Promise<T> {
  nonFinalAttempts += 1
  try {
    return await factory()
  } finally {
    nonFinalAttempts -= 1
  }
}

export async function retryImport<T>(factory: () => Promise<T>): Promise<T> {
  for (const delay of RETRY_DELAYS_MS) {
    try {
      return await nonFinalAttempt(factory)
    } catch {
      await wait(delay)
    }
  }
  return factory()
}

export const lazyWithRetry: typeof lazy = (factory) => lazy(() => retryImport(factory))

export function shouldAutoReload(storage: ReloadStorage, now: number): boolean {
  try {
    const last = Number(storage.getItem(CHUNK_RELOAD_STORAGE_KEY))
    if (last > 0 && now >= last && now - last < CHUNK_RELOAD_WINDOW_MS) return false
    storage.setItem(CHUNK_RELOAD_STORAGE_KEY, String(now))
    return true
  } catch {
    return false
  }
}

function guardedReload({ storage, now = Date.now(), reload }: ReloadDeps): boolean {
  let target: ReloadStorage
  try {
    target = storage ?? window.sessionStorage
  } catch {
    return false
  }
  if (!shouldAutoReload(target, now)) return false
  if (reload) reload()
  else window.location.reload()
  return true
}

export function reloadOnChunkError(error: unknown, deps: ReloadDeps = {}): boolean {
  return isChunkLoadError(error) && guardedReload(deps)
}

const preloadErrorTargets = new WeakSet<EventTarget>()

export function installPreloadErrorReload(
  target: EventTarget = window,
  { now = Date.now, ...deps }: Omit<ReloadDeps, 'now'> & { now?: () => number } = {},
) {
  if (preloadErrorTargets.has(target)) return
  preloadErrorTargets.add(target)
  target.addEventListener('vite:preloadError', (event) => {
    // Vite fires this for every failed import attempt; retryImport still has attempts left for these.
    if (nonFinalAttempts > 0) return
    if (guardedReload({ ...deps, now: now() })) event.preventDefault()
  })
}
