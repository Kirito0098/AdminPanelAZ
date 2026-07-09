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

export function shouldRedirectToAccessUrl(accessUrl: string): boolean {
  if (!accessUrl || typeof window === 'undefined') return false
  try {
    const target = new URL(accessUrl, window.location.origin)
    const current = new URL(window.location.href)
    const targetPath = target.pathname.replace(/\/+$/, '') || '/'
    const currentPath = current.pathname.replace(/\/+$/, '') || '/'
    return target.origin !== current.origin || targetPath !== currentPath
  } catch {
    return false
  }
}

export function redirectToAccessUrl(accessUrl: string, replace = false): void {
  if (!accessUrl || typeof window === 'undefined') return
  if (replace) window.location.replace(accessUrl)
  else window.location.assign(accessUrl)
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

export function withAccessPath(path: string): string {
  if (!accessPath) return path.startsWith('/') ? path : `/${path}`
  const normalized = path.startsWith('/') ? path : `/${path}`
  if (normalized === '/') return `${accessPath}/`
  return `${accessPath}${normalized}`
}

export function publicApiUrl(path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`
  return `${window.location.origin}${apiBase}${normalized}`
}
