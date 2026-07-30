declare global {
  interface Window {
    __PANEL_ACCESS_PATH__?: string
  }
}

function normalizeAccessPath(raw: string | undefined | null): string {
  const value = (raw ?? '').trim()
  if (!value || value === '/') return ''
  const withSlash = value.startsWith('/') ? value : `/${value}`
  return withSlash.replace(/\/+$/, '')
}

export function normalizeAccessPathInput(raw: string | undefined | null): string {
  return normalizeAccessPath(raw)
}

export function apiBaseForAccessPath(path: string | undefined | null): string {
  const normalized = normalizeAccessPath(path)
  return normalized ? `${normalized}/api` : '/api'
}

function readAccessPath(): string {
  if (typeof window !== 'undefined' && window.__PANEL_ACCESS_PATH__) {
    return normalizeAccessPath(window.__PANEL_ACCESS_PATH__)
  }
  return normalizeAccessPath(import.meta.env.VITE_ACCESS_PATH as string | undefined)
}

export const accessPath = readAccessPath()
export const routerBasename = accessPath || undefined
export const apiBase = accessPath ? `${accessPath}/api` : '/api'

export function publicApiUrl(path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`
  return `${window.location.origin}${apiBase}${normalized}`
}
