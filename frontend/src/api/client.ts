const API_BASE = import.meta.env.VITE_API_URL || '/api'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

function getToken(): string | null {
  return localStorage.getItem('token')
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!response.ok) {
    let detail = 'Ошибка запроса'
    try {
      const data = await response.json()
      detail = data.detail || detail
    } catch {
      detail = await response.text()
    }
    throw new ApiError(typeof detail === 'string' ? detail : JSON.stringify(detail), response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

export async function login(username: string, password: string) {
  return apiFetch<{ access_token: string }>('/auth/login/json', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export async function getMe() {
  return apiFetch<import('../types').User>('/auth/me')
}

export async function changePassword(current: string, newPassword: string) {
  return apiFetch('/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current_password: current, new_password: newPassword }),
  })
}

export async function getConfigs() {
  return apiFetch<import('../types').VpnConfig[]>('/configs')
}

export async function createConfig(data: {
  client_name: string
  vpn_type: import('../types').VpnType
  cert_expire_days?: number
  description?: string
  owner_id?: number
}) {
  return apiFetch<import('../types').VpnConfig>('/configs', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function deleteConfig(id: number) {
  return apiFetch(`/configs/${id}`, { method: 'DELETE' })
}

export async function syncConfigs() {
  return apiFetch('/configs/sync', { method: 'POST' })
}

export async function getMonitoring() {
  return apiFetch<import('../types').MonitoringOverview>('/monitoring/overview')
}

export async function getSettings() {
  return apiFetch<import('../types').AppSettings>('/settings')
}

export async function updateSettings(data: Partial<import('../types').AppSettings>) {
  return apiFetch<import('../types').AppSettings>('/settings', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function getUsers() {
  return apiFetch<import('../types').User[]>('/users')
}

export async function createUser(data: {
  username: string
  password: string
  role: import('../types').UserRole
}) {
  return apiFetch<import('../types').User>('/users', {
    method: 'POST',
    body: JSON.stringify({ ...data, theme: 'dark', is_active: true }),
  })
}

export async function deleteUser(id: number) {
  return apiFetch(`/users/${id}`, { method: 'DELETE' })
}

export async function updateUser(id: number, data: Record<string, unknown>) {
  return apiFetch<import('../types').User>(`/users/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function downloadProfile(configId: number, path: string) {
  const token = getToken()
  const url = `${API_BASE}/configs/${configId}/download?path=${encodeURIComponent(path)}`
  return fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
}
