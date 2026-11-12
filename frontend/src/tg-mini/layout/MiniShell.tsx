import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'
import { getTgMiniPublicConfig } from '@/tg-mini/api'
import { openExternalLink } from '@/tg-mini/lib/shareDownloadLink'
import { Button } from '@/components/ui/button'
import Spinner from '@/components/ui/Spinner'
import MiniBottomNav from '@/tg-mini/components/MiniBottomNav'

export default function MiniShell() {
  const { status, error, settings, features, isAdmin, retryAuth } = useTgAuth()
  const [botUsername, setBotUsername] = useState<string | null>(null)

  useEffect(() => {
    if (status !== 'error' && status !== 'no-telegram') return
    let alive = true
    void getTgMiniPublicConfig()
      .then((data) => {
        if (alive) setBotUsername(data.bot_username)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [status])

  if (status === 'loading') {
    return (
      <div className="tg-mini-center">
        <Spinner />
        <p className="tg-mini-muted">Авторизация...</p>
      </div>
    )
  }

  if (status === 'no-telegram' || status === 'error') {
    const botUrl = botUsername ? `https://t.me/${botUsername}` : null
    return (
      <div className="tg-mini-center tg-mini-error-panel">
        <h1 className="text-lg font-semibold">AdminPanelAZ Mini</h1>
        {status === 'no-telegram' ? (
          <p className="tg-mini-muted">
            Откройте Mini App кнопкой в боте
            {botUsername ? ` @${botUsername}` : ''}: браузер не передаёт данные Telegram.
          </p>
        ) : (
          <>
            <p className="tg-mini-muted">
              Возможно, аккаунт Telegram не привязан к панели. Откройте бота и отправьте{' '}
              <code className="font-mono">/link &lt;код&gt;</code> — код выдаёт администратор в панели,
              раздел «Мой профиль».
            </p>
            {error && <p className="tg-mini-muted text-xs">{error}</p>}
          </>
        )}
        <div className="flex flex-wrap items-center justify-center gap-2">
          {botUrl && (
            <Button type="button" onClick={() => openExternalLink(botUrl)}>
              Открыть бота
            </Button>
          )}
          {status === 'error' && (
            <Button type="button" variant={botUrl ? 'outline' : 'default'} onClick={() => void retryAuth()}>
              Повторить
            </Button>
          )}
        </div>
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

      <MiniBottomNav isAdmin={isAdmin} features={features} />
    </div>
  )
}
