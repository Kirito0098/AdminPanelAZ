import { useEffect, useState } from 'react'
import { Copy, ExternalLink, Link2, Link2Off, Send } from 'lucide-react'
import { ApiError, getTelegramBotInfo, getTelegramLinkCode, updateUser } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuth } from '@/context/AuthContext'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'

export default function PersonalTelegramCard() {
  const { isEnabled } = useFeatureModules()
  const { user, refreshUser } = useAuth()
  const { success, error: notifyError } = useNotifications()
  const [linkCode, setLinkCode] = useState<string | null>(null)
  const [expiresIn, setExpiresIn] = useState<number | null>(null)
  const [loadingCode, setLoadingCode] = useState(false)
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

  const handleGetLinkCode = async () => {
    setLoadingCode(true)
    try {
      const result = await getTelegramLinkCode()
      setLinkCode(result.code)
      setExpiresIn(result.expires_in_seconds)
      success(`Код привязки создан (действует ${result.expires_in_seconds} сек)`)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка получения кода')
    } finally {
      setLoadingCode(false)
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
    <>
      <div className="md:col-span-2">
        <h3 className="text-sm font-semibold tracking-tight">Telegram</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">Привязка аккаунта к боту панели</p>
      </div>
      <Card className="overflow-hidden shadow-sm md:col-span-2">
        <div className="h-1 bg-gradient-to-r from-sky-500/70 to-sky-500/15" />
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Send size={18} />
            Telegram
          </CardTitle>
          <CardDescription>
            Привяжите Telegram к аккаунту панели, чтобы пользоваться ботом и Mini App
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border bg-muted/20 p-4">
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
              <div className="rounded-xl border bg-muted/20 p-4">
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
                Получите одноразовый код и отправьте боту
                {botLink ? <> ({botLink})</> : null} команду{' '}
                <code className="rounded bg-muted px-1 py-0.5">/link &lt;код&gt;</code>. Код действует
                ограниченное время.
              </p>
              {linkCode ? (
                <div className="rounded-lg border border-dashed bg-muted/30 p-4">
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
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={loadingCode}
                      onClick={() => void handleGetLinkCode()}
                    >
                      <Link2 size={14} className="mr-1.5" />
                      Новый код
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    className="gap-1.5"
                    disabled={loadingCode}
                    onClick={() => void handleGetLinkCode()}
                  >
                    <Link2 size={16} />
                    {loadingCode ? 'Создание…' : 'Получить код для привязки'}
                  </Button>
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
    </>
  )
}
