// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { API_BASE } from './http'
import { openTicketEventSource } from './streamTicket'
import { setAccessToken } from '@/lib/accessToken'

class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  closed = false
  onmessage: ((event: MessageEvent) => void) | null = null
  private listeners = new Map<string, ((event: Event) => void)[]>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: (event: Event) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener])
  }

  close() {
    this.closed = true
  }

  emit(type: string, event: Event) {
    for (const listener of this.listeners.get(type) ?? []) listener(event)
  }
}

function ticketJson(ticket: string) {
  return new Response(JSON.stringify({ ticket, expires_in_seconds: 30 }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function ticketFetch(...tickets: string[]) {
  const queue = [...tickets]
  return vi.fn(async () => ticketJson(queue.shift() ?? 'exhausted'))
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 10))

describe('openTicketEventSource', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    setAccessToken(null)
  })

  it('opens the stream with a one-time ticket instead of the access token', async () => {
    setAccessToken('secret-access-token')
    const fetchMock = ticketFetch('t1')
    vi.stubGlobal('fetch', fetchMock)
    const attach = vi.fn()

    const handle = openTicketEventSource({
      stream: 'monitoring',
      path: '/monitoring/stream',
      params: { scope: 'node' },
      attach,
    })

    await vi.waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))
    const source = FakeEventSource.instances[0]
    expect(source.url).toBe(`${API_BASE}/monitoring/stream?scope=node&ticket=t1`)
    expect(source.url).not.toContain('secret-access-token')
    expect(attach).toHaveBeenCalledWith(source)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe(`${API_BASE}/stream-ticket`)
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({ stream: 'monitoring' })

    handle.close()
    expect(source.closed).toBe(true)
  })

  it('reconnects with a fresh ticket when the connection drops', async () => {
    vi.stubGlobal('fetch', ticketFetch('t1', 't2'))
    const handle = openTicketEventSource({
      stream: 'monitoring',
      path: '/monitoring/stream',
      attach: vi.fn(),
      reconnectDelayMs: 0,
    })
    await vi.waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))

    FakeEventSource.instances[0].emit('error', new Event('error'))

    await vi.waitFor(() => expect(FakeEventSource.instances).toHaveLength(2))
    expect(FakeEventSource.instances[0].closed).toBe(true)
    expect(FakeEventSource.instances[1].url).toContain('ticket=t2')
    handle.close()
  })

  it('reports a dropped connection once when reconnect is off', async () => {
    vi.stubGlobal('fetch', ticketFetch('t1', 't2'))
    const onError = vi.fn()
    openTicketEventSource({
      stream: 'warper_update',
      path: '/warper/updates/stream',
      attach: vi.fn(),
      onError,
      connectionLostMessage: 'Соединение прервано',
    })
    await vi.waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))

    FakeEventSource.instances[0].emit('error', new Event('error'))
    await tick()

    expect(onError).toHaveBeenCalledTimes(1)
    expect(onError).toHaveBeenCalledWith('Соединение прервано')
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(FakeEventSource.instances[0].closed).toBe(true)
  })

  it('leaves server-sent error events to the stream handler', async () => {
    vi.stubGlobal('fetch', ticketFetch('t1'))
    const onError = vi.fn()
    const handle = openTicketEventSource({
      stream: 'monitoring',
      path: '/monitoring/stream',
      attach: vi.fn(),
      onError,
      reconnectDelayMs: 0,
    })
    await vi.waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))

    FakeEventSource.instances[0].emit('error', new MessageEvent('error', { data: '{"detail":"x"}' }))
    await tick()

    expect(FakeEventSource.instances[0].closed).toBe(false)
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(onError).not.toHaveBeenCalled()
    handle.close()
  })

  it('does not open a stream that was closed before the ticket arrived', async () => {
    let release!: () => void
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        await gate
        return ticketJson('t1')
      }),
    )

    const handle = openTicketEventSource({ stream: 'awg2_install', path: '/awg2/install/stream', attach: vi.fn() })
    handle.close()
    release()
    await tick()

    expect(FakeEventSource.instances).toHaveLength(0)
  })

  it('reports a refused ticket', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: 'Требуются права администратора' }), {
            status: 403,
            headers: { 'Content-Type': 'application/json' },
          }),
      ),
    )
    const onError = vi.fn()

    openTicketEventSource({ stream: 'awg2_install', path: '/awg2/install/stream', attach: vi.fn(), onError })

    await vi.waitFor(() => expect(onError).toHaveBeenCalledWith('Требуются права администратора'))
    expect(FakeEventSource.instances).toHaveLength(0)
  })
})
