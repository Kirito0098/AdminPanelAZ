const START_PARAM_ROUTES: Record<string, string> = {
  configs: '/configs',
  clients: '/clients',
  requests: '/requests',
  settings: '/settings',
  'unlock-codes': '/unlock-codes',
}

export function mapTelegramStartParam(startParam: string | null | undefined): string | null {
  const normalized = startParam?.trim().toLowerCase()
  if (!normalized) return null

  return Object.prototype.hasOwnProperty.call(START_PARAM_ROUTES, normalized)
    ? START_PARAM_ROUTES[normalized]
    : null
}
