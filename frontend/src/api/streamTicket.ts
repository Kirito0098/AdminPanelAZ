import { API_BASE, apiFetch } from './http'

export type StreamName = 'monitoring' | 'warper_update' | 'awg2_install' | 'server_monitor'

export interface StreamHandle {
  close: () => void
}

export async function getStreamTicket(stream: StreamName): Promise<string> {
  const { ticket } = await apiFetch<{ ticket: string; expires_in_seconds: number }>('/stream-ticket', {
    method: 'POST',
    body: JSON.stringify({ stream }),
  })
  return ticket
}

export function openTicketEventSource(options: {
  stream: StreamName
  path: string
  params?: Record<string, string>
  attach: (source: EventSource) => void
  onError?: (message: string) => void
  connectionLostMessage?: string
  reconnectDelayMs?: number
}): StreamHandle {
  let source: EventSource | null = null
  let timer: ReturnType<typeof setTimeout> | undefined
  let closed = false

  const scheduleReconnect = () => {
    if (closed || options.reconnectDelayMs == null) return
    timer = setTimeout(() => void connect(), options.reconnectDelayMs)
  }

  const connect = async () => {
    let ticket: string
    try {
      ticket = await getStreamTicket(options.stream)
    } catch (err) {
      if (closed) return
      options.onError?.(err instanceof Error ? err.message : 'Не удалось открыть поток')
      scheduleReconnect()
      return
    }
    if (closed) return
    const query = new URLSearchParams({ ...options.params, ticket })
    const current = new EventSource(`${API_BASE}${options.path}?${query.toString()}`)
    source = current
    options.attach(current)
    current.addEventListener('error', (event) => {
      if (event instanceof MessageEvent) return
      current.close()
      if (source === current) source = null
      if (closed) return
      if (options.reconnectDelayMs != null) {
        scheduleReconnect()
      } else {
        options.onError?.(options.connectionLostMessage ?? 'Соединение с потоком прервано')
      }
    })
  }

  void connect()

  return {
    close: () => {
      closed = true
      if (timer !== undefined) clearTimeout(timer)
      source?.close()
      source = null
    },
  }
}
