import { getWebSessionId } from '@/lib/webSession'
import { clearAccessToken } from '@/lib/accessToken'
import { applyExpectedNodeHeader } from '@/lib/expectedNode'
import {
  API_BASE,
  apiFetch,
  getToken,
  isNodeAgentAuthFailureDetail,
  parseApiError,
  refreshAccessToken,
} from './http'
import type {
  Awg2HealthResponse,
  Awg2StatusResponse,
  Awg2ObfuscationResponse,
  Awg2MonitoringResponse,
  Awg2ClientStats,
  Awg2InstallStreamEvent,
  Awg2RestoreResponse,
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

export async function getAwg2Monitoring() {
  return apiFetch<Awg2MonitoringResponse>('/awg2/monitoring')
}

export async function getAwg2ClientStats(clientName: string) {
  return apiFetch<Awg2ClientStats>(`/awg2/clients/${encodeURIComponent(clientName)}/stats`)
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
): EventSource | null {
  const token = getToken()
  if (!token) return null
  const params = new URLSearchParams({
    token,
    mode: options.mode,
  })
  if (options.preset?.trim()) params.set('preset', options.preset.trim())
  if (options.template?.trim()) params.set('template', options.template.trim())
  if (options.mtu != null && Number.isFinite(options.mtu)) params.set('mtu', String(options.mtu))
  const source = new EventSource(`${API_BASE}/awg2/install/stream?${params.toString()}`)
  source.onmessage = (event) => {
    try {
      onEvent(JSON.parse(event.data) as Awg2InstallStreamEvent)
    } catch {
      onError?.('Ошибка разбора потока установки AZ-AWG2')
    }
  }
  source.onerror = () => {
    onError?.('Соединение с потоком установки прервано')
  }
  return source
}

export async function restoreAwg2Backup(file: File) {
  const form = new FormData()
  form.append('archive', file)
  return apiFetch<Awg2RestoreResponse>('/awg2/restore', {
    method: 'POST',
    body: form,
  })
}

export async function downloadAwg2Backup(retry = true): Promise<Response> {
  const headers = new Headers()
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const sessionId = getWebSessionId()
  if (sessionId) headers.set('X-Web-Session-Id', sessionId)
  applyExpectedNodeHeader(headers, 'POST')

  const response = await fetch(`${API_BASE}/awg2/backup`, {
    method: 'POST',
    headers,
    credentials: 'include',
  })
  if (response.status === 401 && retry) {
    const peek = await response.clone().json().catch(() => null)
    const detail = peek && typeof peek === 'object' ? (peek as { detail?: unknown }).detail : undefined
    if (isNodeAgentAuthFailureDetail(detail)) {
      throw await parseApiError(response, 'Ошибка скачивания бэкапа AZ-AWG2')
    }
    const newToken = await refreshAccessToken()
    if (newToken) {
      return downloadAwg2Backup(false)
    }
    clearAccessToken()
  }
  if (!response.ok) {
    throw await parseApiError(response, 'Ошибка скачивания бэкапа AZ-AWG2')
  }
  return response
}
