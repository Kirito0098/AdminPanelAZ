import { Navigate, useLocation } from 'react-router-dom'

type RouteRedirectProps = {
  /** Новый путь; query в самой строке (`/monitoring?scope=host`) — стартовые параметры. */
  to: string
  /** Значение `tab` на новой странице: всегда побеждает одноимённый старый параметр. */
  tab?: string
  /** Старое имя параметра → новое. Остальные параметры переносятся как есть. */
  paramMap?: Record<string, string>
}

/**
 * Редирект со старого URL на новый с сохранением query: закладки и deep links
 * (`/traffic?client=X`, `/logs?tab=openvpn-sockets`) должны открывать ту же вкладку.
 */
export default function RouteRedirect({ to, tab, paramMap }: RouteRedirectProps) {
  const { search, hash } = useLocation()
  const [pathname, targetQuery = ''] = to.split('?')
  const params = new URLSearchParams(targetQuery)

  for (const [key, value] of new URLSearchParams(search)) {
    const nextKey = paramMap?.[key] ?? key
    // Новая вкладка задаётся пропом и не должна перетираться старым `tab`.
    if (nextKey === 'tab') continue
    params.set(nextKey, value)
  }
  if (tab) params.set('tab', tab)

  return <Navigate to={{ pathname, search: params.toString(), hash }} replace />
}
