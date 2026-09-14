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

const TG_MINI_PATH_RE = /^(.*)\/api\/tg-mini(?:\/|$)/

export function resolveAccessPath(input: {
  pathname?: string
  injected?: string | null
  viteEnv?: string | null
}): string {
  const pathname = input.pathname || ''
  if (pathname === '/p' || pathname.startsWith('/p/')) {
    return ''
  }
  if (input.injected) {
    return normalizeAccessPath(input.injected)
  }
  const match = pathname.match(TG_MINI_PATH_RE)
  if (match) {
    return normalizeAccessPath(match[1] || '')
  }
  return normalizeAccessPath(input.viteEnv)
}

function readAccessPath(): string {
  if (typeof window !== 'undefined') {
    return resolveAccessPath({
      pathname: window.location.pathname || '',
      injected: window.__PANEL_ACCESS_PATH__,
      viteEnv: import.meta.env.VITE_ACCESS_PATH as string | undefined,
    })
  }
  return resolveAccessPath({
    pathname: '',
    injected: undefined,
    viteEnv: import.meta.env.VITE_ACCESS_PATH as string | undefined,
  })
}

export const accessPath = readAccessPath()
export const routerBasename = accessPath || undefined
export const apiBase = accessPath ? `${accessPath}/api` : '/api'

export function publicApiUrl(path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`
  return `${window.location.origin}${apiBase}${normalized}`
}
