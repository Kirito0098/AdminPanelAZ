import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/http'
import { SERVER_UNAVAILABLE_MESSAGE, loadSessionUser } from './authBoot'
import type { User } from '@/types'

const alice = { id: 1, username: 'alice' } as User

afterEach(() => {
  vi.useRealTimers()
})

describe('loadSessionUser', () => {
  it('uses the token in memory without refreshing', async () => {
    const refresh = vi.fn()
    const result = await loadSessionUser({ getToken: () => 't', refresh, getMe: async () => alice })
    expect(result).toEqual({ kind: 'user', user: alice })
    expect(refresh).not.toHaveBeenCalled()
  })

  it('refreshes when there is no token and loads the user', async () => {
    const getMe = vi.fn(async () => alice)
    const result = await loadSessionUser({ getToken: () => null, refresh: async () => 'new', getMe })
    expect(result).toEqual({ kind: 'user', user: alice })
    expect(getMe).toHaveBeenCalledTimes(1)
  })

  it('is anonymous when the server refuses the session', async () => {
    const getMe = vi.fn()
    expect(await loadSessionUser({ getToken: () => null, refresh: async () => null, getMe })).toEqual({
      kind: 'anonymous',
    })
    expect(getMe).not.toHaveBeenCalled()
    for (const status of [401, 403]) {
      const failing = async () => {
        throw new ApiError('no', status)
      }
      expect(await loadSessionUser({ getToken: () => 't', refresh: async () => 't', getMe: failing })).toEqual({
        kind: 'anonymous',
      })
    }
  })

  it('reports an unreachable server instead of hanging or logging out', async () => {
    const network = async (): Promise<string | null> => {
      throw new TypeError('Failed to fetch')
    }
    expect(await loadSessionUser({ getToken: () => null, refresh: network, getMe: async () => alice })).toEqual({
      kind: 'unavailable',
      message: SERVER_UNAVAILABLE_MESSAGE,
    })
  })

  it('uses its own message for a connection failure reported by apiFetch', async () => {
    const offline = async (): Promise<string | null> => {
      throw new ApiError('Не удалось связаться с сервером.', 0)
    }
    expect(await loadSessionUser({ getToken: () => null, refresh: offline, getMe: async () => alice })).toEqual({
      kind: 'unavailable',
      message: SERVER_UNAVAILABLE_MESSAGE,
    })
  })

  it('passes the server message of other errors through', async () => {
    const badGateway = async (): Promise<string | null> => {
      throw new ApiError('Сервер временно недоступен (502).', 502)
    }
    expect(await loadSessionUser({ getToken: () => null, refresh: badGateway, getMe: async () => alice })).toEqual({
      kind: 'unavailable',
      message: 'Сервер временно недоступен (502).',
    })
    const notFound = async (): Promise<User> => {
      throw new ApiError('Запрос не найден (404).', 404)
    }
    expect(await loadSessionUser({ getToken: () => 't', refresh: async () => 't', getMe: notFound })).toEqual({
      kind: 'unavailable',
      message: 'Запрос не найден (404).',
    })
  })

  it('gives up on a server that never answers', async () => {
    vi.useFakeTimers()
    const pending = loadSessionUser({
      getToken: () => null,
      refresh: () => new Promise<string | null>(() => {}),
      getMe: async () => alice,
      timeoutMs: 1000,
    })
    await vi.advanceTimersByTimeAsync(999)
    let settled = false
    void pending.then(() => {
      settled = true
    })
    await Promise.resolve()
    expect(settled).toBe(false)
    await vi.advanceTimersByTimeAsync(1)
    expect(await pending).toEqual({ kind: 'unavailable', message: SERVER_UNAVAILABLE_MESSAGE })
  })

  it('does not leave the timer running after an answer', async () => {
    vi.useFakeTimers()
    await loadSessionUser({ getToken: () => 't', refresh: async () => 't', getMe: async () => alice })
    expect(vi.getTimerCount()).toBe(0)
  })
})
