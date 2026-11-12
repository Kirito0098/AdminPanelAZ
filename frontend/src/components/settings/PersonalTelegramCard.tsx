import { useEffect, useState } from 'react'
import { Copy, ExternalLink, Link2Off, Send } from 'lucide-react'
import { ApiError, getTelegramBotInfo, getTelegramLinkCode, updateUser } from '@/api/client'
import TelegramLinkCodeForm from '@/components/telegram/TelegramLinkCodeForm'
import { Button } from '@/components/ui/button'
import {
  SettingsCard as Card,
  SettingsCardContent as CardContent,
  SettingsCardDescription as CardDescription,
  SettingsCardHeader as CardHeader,
  SettingsCardTitle as CardTitle,
} from '@/components/settings/SettingsCard'
import { useAuth } from '@/context/AuthContext'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'

export default function PersonalTelegramCard() {
  const { isEnabled } = useFeatureModules()
  const { user, refreshUser } = useAuth()
  const { success, error: notifyError } = useNotifications()
  const [linkCode, setLinkCode] = useState<string | null>(null)
  const [expiresIn, setExpiresIn] = useState<number | null>(null)
  const [unlinking, setUnlinking] = useState(false)
  const [botUsername, setBotUsername] = useState('')
  const [botUrl, setBotUrl] = useState('')

  useEffect(() => {
    if (!isEnabled('telegram')) return
    let cancelled = false
    void getTelegramBotInfo()
      .then((info) => {
        if (cancelled) return
        setBotUsername(info.bot_username || '')
        setBotUrl(info.bot_url || '')
      })
      .catch(() => {
        /* bot username optional — linking still works without it */
      })
    return () => {
      cancelled = true
    }
  }, [isEnabled])

  if (!isEnabled('telegram') || !user) return null

  const telegramId = user.telegram_id?.trim() || ''
  const linked = Boolean(telegramId)

  const handleGetLinkCode = async (currentPassword: string) => {
    try {
      const result = await getTelegramLinkCode(currentPassword)
      setLinkCode(result.code)
      setExpiresIn(result.expires_in_seconds)
      const command = `/link ${result.code}`
      try {
        await navigator.clipboard.writeText(command)
        success(`Код скопирован (действует ${result.expires_in_seconds} сек)`)
      } catch {
        success(`Код привязки создан (действует ${result.expires_in_seconds} сек)`)
      }
      return true
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка получения кода')
      return false
    }
  }

  const handleCopyLinkCode = async () => {
    if (!linkCode) return
    try {
      await navigator.clipboard.writeText(`/link ${linkCode}`)
      success('Команда /link скопирована')
    } catch {
      notifyError('Не удалось скопировать')
    }
  }

  const handleUnlink = async () => {
    setUnlinking(true)
    try {
      await updateUser(user.id, { telegram_id: '' })
      setLinkCode(null)
      setExpiresIn(null)
      await refreshUser()
      success('Telegram отвязан от аккаунта')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось отвязать Telegram')
    } finally {
      setUnlinking(false)
    }
  }

  const botLink = botUrl ? (
    <a
      href={botUrl}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 font-medium text-primary underline-offset-4 hover:underline"
    >
      @{botUsername}
      <ExternalLink className="h-3 w-3" />
    </a>
  ) : null

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Send size={16} aria-hidden />
          </span>
          <div className="min-w-0">
            <CardTitle>Telegram</CardTitle>
            <CardDescription className="mt-0.5">
              Привяжите Telegram к аккаунту панели, чтобы пользоваться ботом и Mini App
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div
            className={
              linked
                ? 'rounded-lg border border-primary/20 bg-primary/5 p-3 sm:p-4'
                : 'rounded-lg border border-border/70 bg-muted/20 p-3 sm:p-4'
            }
          >
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Статус</p>
            {linked ? (
              <p className="mt-1 text-sm font-semibold">
                Привязан · <span className="font-mono">{telegramId}</span>
              </p>
            ) : (
              <p className="mt-1 text-sm font-semibold">Не привязан</p>
            )}
          </div>
          {botUrl ? (
            <div className="rounded-lg border border-border/70 bg-muted/20 p-3 sm:p-4">
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Бот</p>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                {botLink}
                <Button type="button" variant="secondary" size="sm" asChild>
                  <a href={botUrl} target="_blank" rel="noreferrer">
                    <ExternalLink size={14} className="mr-1.5" />
                    Открыть бота
                  </a>
                </Button>
              </div>
            </div>
          ) : null}
        </div>

        {linked ? (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-muted-foreground">
              После отвязки бот перестанет узнавать этот аккаунт, пока вы не привяжете Telegram снова.
              {botUrl ? (
                <>
                  {' '}
                  Бот: {botLink}
                </>
              ) : null}
            </p>
            <Button
              type="button"
              variant="outline"
              className="w-full gap-1.5 sm:w-auto sm:shrink-0"
              disabled={unlinking}
              onClick={() => void handleUnlink()}
            >
              <Link2Off size={16} />
              {unlinking ? 'Отвязка…' : 'Отвязать'}
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              Введите текущий пароль, получите одноразовый код и отправьте боту
              {botLink ? <> ({botLink})</> : null} команду{' '}
              <code className="rounded bg-muted px-1 py-0.5">/link &lt;код&gt;</code>. Код действует
              ограниченное время.
            </p>
            {linkCode ? (
              <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 sm:p-4">
                <p className="text-xs text-muted-foreground">
                  Отправьте боту в Telegram
                  {expiresIn != null ? ` · действует ${expiresIn} сек` : ''}
                </p>
                <p className="mt-1 font-mono text-lg font-semibold tracking-wide">/link {linkCode}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button type="button" variant="secondary" size="sm" onClick={() => void handleCopyLinkCode()}>
                    <Copy size={14} className="mr-1.5" />
                    Скопировать команду
                  </Button>
                  {botUrl ? (
                    <Button type="button" variant="secondary" size="sm" asChild>
                      <a href={botUrl} target="_blank" rel="noreferrer">
                        <ExternalLink size={14} className="mr-1.5" />
                        Открыть бота
                      </a>
                    </Button>
                  ) : null}
                  <Button type="button" variant="outline" size="sm" onClick={() => setLinkCode(null)}>
                    Новый код
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <TelegramLinkCodeForm idPrefix="personal-telegram" onRequest={handleGetLinkCode} />
                {botUrl ? (
                  <Button type="button" variant="outline" className="gap-1.5" asChild>
                    <a href={botUrl} target="_blank" rel="noreferrer">
                      <ExternalLink size={16} />
                      Открыть бота
                    </a>
                  </Button>
                ) : null}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
