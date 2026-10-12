import {
  apiFetch,
  apiFetchResponse,
} from './http'
import { openTicketEventSource, type StreamHandle } from './streamTicket'
import type {
  Awg2HealthResponse,
  Awg2StatusResponse,
  Awg2ObfuscationResponse,
  Awg2InstallStreamEvent,
} from '../types'

export async function getAwg2Health() {
  return apiFetch<Awg2HealthResponse>('/awg2/health')
}

export async function getAwg2Status() {
  return apiFetch<Awg2StatusResponse>('/awg2/status')
}

export async function getAwg2Obfuscation() {
  return apiFetch<Awg2ObfuscationResponse>('/awg2/obfuscation')
}

export async function regenerateAwg2Obfuscation() {
  return apiFetch<Awg2ObfuscationResponse>('/awg2/obfuscation/regenerate', {
    method: 'POST',
  })
}

export async function applyAwg2Obfuscation(payload: {
  preset: string
  template: string
  mtu?: number | null
  host?: string | null
  fp?: string | null
}) {
  return apiFetch<Awg2ObfuscationResponse>('/awg2/obfuscation/apply', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function openAwg2InstallStream(
  options: {
    mode: 'install' | 'update'
    preset?: string
    template?: string
    mtu?: number | null
  },
  onEvent: (event: Awg2InstallStreamEvent) => void,
  onError?: (message: string) => void,
): StreamHandle {
  const params: Record<string, string> = { mode: options.mode }
  if (options.preset?.trim()) params.preset = options.preset.trim()
  if (options.template?.trim()) params.template = options.template.trim()
  if (options.mtu != null && Number.isFinite(options.mtu)) params.mtu = String(options.mtu)
  return openTicketEventSource({
    stream: 'awg2_install',
    path: '/awg2/install/stream',
    params,
    onError,
    connectionLostMessage: 'Соединение с потоком установки прервано',
    attach: (source) => {
      source.onmessage = (event) => {
        try {
          onEvent(JSON.parse(event.data) as Awg2InstallStreamEvent)
        } catch {
          onError?.('Ошибка разбора потока установки AZ-AWG2')
        }
      }
    },
  })
}

export function downloadAwg2Backup() {
  return apiFetchResponse('/awg2/backup', { method: 'POST' })
}
