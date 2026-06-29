import { Outlet } from 'react-router-dom'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'
import { Button } from '@/components/ui/button'
import Spinner from '@/components/ui/Spinner'
import MiniBottomNav from '@/tg-mini/components/MiniBottomNav'

export default function MiniShell() {
  const { status, error, settings, isAdmin, retryAuth } = useTgAuth()

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

      <MiniBottomNav isAdmin={isAdmin} />
    </div>
  )
}
