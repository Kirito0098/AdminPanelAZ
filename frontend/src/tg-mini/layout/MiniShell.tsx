import { NavLink, Outlet } from 'react-router-dom'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'
import { Button } from '@/components/ui/button'
import Spinner from '@/components/ui/Spinner'
import { cn } from '@/lib/utils'

const baseTabs = [
  { to: '/', label: 'Дашборд', end: true },
  { to: '/configs', label: 'Конфиги' },
  { to: '/settings', label: 'Настройки' },
]

export default function MiniShell() {
  const { status, error, settings, isAdmin, retryAuth } = useTgAuth()
  const tabs = isAdmin
    ? [
        baseTabs[0],
        baseTabs[1],
        { to: '/nodes', label: 'Узлы' },
        { to: '/warper', label: 'WARP' },
        { to: '/cidr', label: 'CIDR' },
        baseTabs[2],
      ]
    : baseTabs

  if (status === 'loading') {
    return (
      <div className="tg-mini-center">
        <Spinner />
        <p className="tg-mini-muted">Авторизация...</p>
      </div>
    )
  }

  if (status === 'no-telegram' || status === 'error') {
    return (
      <div className="tg-mini-center tg-mini-error-panel">
        <h1 className="text-lg font-semibold">AdminPanelAZ Mini</h1>
        <p className="tg-mini-muted">{error || 'Откройте через Telegram'}</p>
        {status === 'error' && (
          <Button type="button" onClick={() => void retryAuth()}>
            Повторить
          </Button>
        )}
      </div>
    )
  }

  return (
    <div className="tg-mini-shell">
      <header className="tg-mini-header">
        <p className="tg-mini-kicker">AdminPanelAZ</p>
        <h1 className="tg-mini-brand">Панель в Telegram</h1>
        <div className="tg-mini-status is-success">
          {settings?.username ? `Подключено: ${settings.username}` : 'Подключено'}
        </div>
      </header>

      <main className="tg-mini-main">
        <Outlet />
      </main>

      <nav
        className={cn('tg-mini-tabs', tabs.length > 3 ? 'tg-mini-tabs-cols-6' : 'tg-mini-tabs-cols-3')}
        aria-label="Mini app tabs"
      >
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) => `tg-mini-tab${isActive ? ' is-active' : ''}`}
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
