import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import {
  Bell,
  Bot,
  CheckCircle2,
  Copy,
  Loader2,
  Send,
  Server,
  Shield,
  User,
} from 'lucide-react'
import { ApiError } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import MetricCard from '@/components/noc/MetricCard'
import {
  LABEL_AUTH_MAX_AGE,
  LABEL_BOT_USERNAME,
  LABEL_CHAT_ID,
  LABEL_TELEGRAM_ID,
} from '@/lib/uiLabels'
import { cn } from '@/lib/utils'
import MiniPageHeader from '@/tg-mini/components/MiniPageHeader'
import MiniSettingToggle from '@/tg-mini/components/MiniSettingToggle'
import { getTgAdminNotify, getTgTelegramSettings, testTgAdminNotify, testTgTelegram, updateTgAdminNotify, updateTgTelegramSettings } from '@/tg-mini/api'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'
import { miniRoleLabel } from '@/tg-mini/lib/settingsMini'
import type { AdminNotifySettings, TelegramSettings } from '@/types'

type Feedback = { tone: 'success' | 'error' | 'info'; text: string }

function SettingsSkeleton() {
  return (
    <div className="tg-mini-dashboard space-y-4" aria-busy="true" aria-label="Загрузка настроек">
      <div className="tg-mini-skeleton" style={{ height: '2.5rem' }} />
      <div className="tg-mini-skeleton tg-mini-skeleton-summary" />
      <div className="tg-mini-cards">
        <div className="tg-mini-skeleton tg-mini-skeleton-card" />
        <div className="tg-mini-skeleton tg-mini-skeleton-card" />
      </div>
      <div className="tg-mini-skeleton tg-mini-skeleton-section" />
      <div className="tg-mini-skeleton tg-mini-skeleton-section" />
    </div>
  )
}

function SectionTitle({ icon: Icon, children }: { icon: typeof User; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <div className="rounded-md bg-muted p-1.5 text-muted-foreground">
        <Icon size={15} aria-hidden />
      </div>
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{children}</p>
    </div>
  )
}

function FeedbackBanner({ feedback }: { feedback: Feedback }) {
  return (
    <div
      className={cn(
        'tg-mini-feedback',
        feedback.tone === 'success' && 'is-success',
        feedback.tone === 'error' && 'is-error',
        feedback.tone === 'info' && 'is-info',
      )}
      role="status"
    >
      {feedback.tone === 'success' ? (
        <CheckCircle2 size={18} className="shrink-0" aria-hidden />
      ) : (
        <Bell size={18} className="shrink-0 opacity-70" aria-hidden />
      )}
      <p className="text-sm leading-snug">{feedback.text}</p>
    </div>
  )
}

function CopyableValue({ value, label }: { value: string; label: string }) {
  const [hint, setHint] = useState<string | null>(null)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
      setHint('Скопировано')
      window.setTimeout(() => setHint(null), 1600)
    } catch {
      setHint('Ошибка')
      window.setTimeout(() => setHint(null), 1600)
    }
  }

  return (
    <button type="button" className="tg-mini-copy-ip tg-mini-copy-ip--inline" onClick={() => void copy()} title={`Скопировать ${label}`}>
      <span className="mono truncate">{value}</span>
      <Copy size={13} className="shrink-0 opacity-60" aria-hidden />
      {hint && <span className="tg-mini-copy-hint">{hint}</span>}
    </button>
  )
}

export default function Settings() {
  const { settings, isAdmin } = useTgAuth()
  const [notify, setNotify] = useState<AdminNotifySettings | null>(null)
  const [telegram, setTelegram] = useState<TelegramSettings | null>(null)
  const [eventToggles, setEventToggles] = useState<Record<string, boolean>>({})
  const [botToken, setBotToken] = useState('')
  const [botUsername, setBotUsername] = useState('')
  const [authMaxAge, setAuthMaxAge] = useState('300')
  const [chatId, setChatId] = useState('')
  const [notifyEnabled, setNotifyEnabled] = useState(false)
  const [notifyOnBackup, setNotifyOnBackup] = useState(false)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [savingNotify, setSavingNotify] = useState(false)
  const [testingNotify, setTestingNotify] = useState(false)
  const [savingTelegram, setSavingTelegram] = useState(false)
  const [testingTelegram, setTestingTelegram] = useState(false)
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [error, setError] = useState<string | null>(null)

  const applyNotify = (data: AdminNotifySettings) => {
    setNotify(data)
    setEventToggles(Object.fromEntries(data.events.map((event) => [event.key, event.enabled])))
  }

  const applyTelegram = (data: TelegramSettings) => {
    setTelegram(data)
    setBotUsername(data.bot_username)
    setAuthMaxAge(String(data.auth_max_age_seconds || 300))
    setChatId(data.chat_id)
    setNotifyEnabled(data.notify_enabled)
    setNotifyOnBackup(data.notify_on_backup)
  }

  const load = useCallback(async (options?: { silent?: boolean }) => {
    const silent = options?.silent ?? false
    if (silent) {
      setRefreshing(true)
    } else {
      setLoading(true)
    }
    setError(null)
    try {
      const notifyPromise = getTgAdminNotify()
      const telegramPromise = isAdmin ? getTgTelegramSettings() : Promise.resolve(null)
      const [notifyData, telegramData] = await Promise.all([notifyPromise, telegramPromise])
      applyNotify(notifyData)
      if (telegramData) applyTelegram(telegramData)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [isAdmin])

  useEffect(() => {
    void load()
  }, [load])

  const handleSaveNotify = async (e: FormEvent) => {
    e.preventDefault()
    setSavingNotify(true)
    setFeedback(null)
    try {
      const updated = await updateTgAdminNotify({ events: eventToggles })
      applyNotify(updated)
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
      setFeedback({ tone: 'success', text: 'Настройки уведомлений сохранены' })
    } catch (err) {
      setFeedback({
        tone: 'error',
        text: err instanceof ApiError ? err.message : 'Ошибка сохранения',
      })
    } finally {
      setSavingNotify(false)
    }
  }

  const handleTestNotify = async () => {
    setTestingNotify(true)
    setFeedback(null)
    try {
      const result = await testTgAdminNotify()
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
      setFeedback({ tone: 'success', text: result.message })
    } catch (err) {
      setFeedback({
        tone: 'error',
        text: err instanceof ApiError ? err.message : 'Ошибка теста',
      })
    } finally {
      setTestingNotify(false)
    }
  }

  const handleSaveTelegram = async (e: FormEvent) => {
    e.preventDefault()
    setSavingTelegram(true)
    setFeedback(null)
    try {
      const maxAge = Number.parseInt(authMaxAge, 10)
      const updated = await updateTgTelegramSettings({
        bot_token: botToken || undefined,
        bot_username: botUsername.trim() || undefined,
        auth_max_age_seconds: Number.isFinite(maxAge) ? maxAge : undefined,
        chat_id: chatId,
        notify_enabled: notifyEnabled,
        notify_on_backup: notifyOnBackup,
      })
      applyTelegram(updated)
      setBotToken('')
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
      setFeedback({ tone: 'success', text: 'Настройки Telegram сохранены' })
    } catch (err) {
      setFeedback({
        tone: 'error',
        text: err instanceof ApiError ? err.message : 'Ошибка сохранения',
      })
    } finally {
      setSavingTelegram(false)
    }
  }

  const handleTestTelegram = async () => {
    setTestingTelegram(true)
    setFeedback(null)
    try {
      const result = await testTgTelegram()
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
      setFeedback({ tone: 'success', text: result.message })
    } catch (err) {
      setFeedback({
        tone: 'error',
        text: err instanceof ApiError ? err.message : 'Ошибка теста бота',
      })
    } finally {
      setTestingTelegram(false)
    }
  }

  if (loading) {
    return <SettingsSkeleton />
  }

  const themeLabel = settings?.theme === 'dark' ? 'Тёмная' : 'Светлая'

  return (
    <div className="tg-mini-dashboard space-y-4">
      <MiniPageHeader
        title="Настройки"
        subtitle="Аккаунт, уведомления и параметры бота"
        onRefresh={() => void load({ silent: true })}
        refreshing={refreshing}
      />

      {error && (
        <div className="tg-mini-inline-alert" role="alert">
          {error}
          <Button type="button" variant="outline" size="sm" className="mt-2" onClick={() => void load()}>
            Повторить
          </Button>
        </div>
      )}

      {feedback && <FeedbackBanner feedback={feedback} />}

      <Card className="tg-mini-warper-hero">
        <CardContent className="space-y-3 p-4">
          <div className="flex items-start gap-3">
            <div className="tg-mini-warper-icon" aria-hidden>
              <User size={22} />
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="truncate text-base font-semibold">{settings?.username ?? '—'}</h3>
              <p className="mt-0.5 text-xs text-muted-foreground">{miniRoleLabel(settings?.role)}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <Badge variant="outline" className="font-normal">
                  Тема: {themeLabel}
                </Badge>
                <Badge
                  variant={settings?.bot_configured ? 'default' : 'outline'}
                  className={cn('gap-1 font-normal', settings?.bot_configured && 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400')}
                >
                  <Bot size={11} aria-hidden />
                  {settings?.bot_configured ? 'Бот настроен' : 'Бот не настроен'}
                </Badge>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="tg-mini-cards">
        <MetricCard
          label="Сервер"
          value={settings?.server_ip ? 'IP' : '—'}
          sub={settings?.server_ip ?? 'не задан'}
          icon={Server}
          accent={settings?.server_ip ? 'cyan' : 'default'}
        />
        <MetricCard
          label="Telegram ID"
          value={notify?.telegram_id ? 'Привязан' : '—'}
          sub={notify?.telegram_id || 'не привязан'}
          icon={Shield}
          accent={notify?.telegram_id ? 'green' : 'amber'}
        />
      </div>

      {settings?.server_ip && (
        <Card>
          <CardContent className="space-y-2 p-4">
            <SectionTitle icon={Server}>IP сервера</SectionTitle>
            <CopyableValue value={settings.server_ip} label="IP сервера" />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="space-y-4 p-4">
          <SectionTitle icon={Bell}>Личные уведомления</SectionTitle>

          <div className="rounded-lg border bg-muted/20 px-3 py-2.5">
            <p className="text-xs text-muted-foreground">{LABEL_TELEGRAM_ID}</p>
            <p className="mono mt-1 text-sm font-medium">{notify?.telegram_id || '—'}</p>
            <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
              Привязка через <span className="font-mono">/link</span> в боте или в веб-панели → Пользователи.
            </p>
          </div>

          <form className="space-y-1" onSubmit={(e) => void handleSaveNotify(e)}>
            {notify?.events.map((event) => (
              <MiniSettingToggle
                key={event.key}
                label={event.label}
                checked={Boolean(eventToggles[event.key])}
                onCheckedChange={(checked) =>
                  setEventToggles((prev) => ({ ...prev, [event.key]: checked }))
                }
              />
            ))}
            <div className="flex flex-wrap gap-2 pt-3">
              <Button type="submit" className="gap-1.5" disabled={savingNotify}>
                {savingNotify ? <Loader2 size={16} className="animate-spin" aria-hidden /> : null}
                Сохранить
              </Button>
              <Button
                type="button"
                variant="outline"
                className="gap-1.5"
                disabled={testingNotify || !notify?.telegram_id}
                onClick={() => void handleTestNotify()}
              >
                {testingNotify ? (
                  <Loader2 size={16} className="animate-spin" aria-hidden />
                ) : (
                  <Send size={16} aria-hidden />
                )}
                Тест
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {isAdmin && telegram && (
        <Card>
          <CardContent className="space-y-4 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <SectionTitle icon={Bot}>Telegram-бот</SectionTitle>
              <div className="flex flex-wrap gap-1.5">
                {telegram.bot_token_set && (
                  <Badge variant="outline" className="text-[10px] font-normal">
                    Токен задан
                  </Badge>
                )}
                {telegram.webhook_registered && (
                  <Badge variant="outline" className="text-[10px] font-normal">
                    Webhook
                  </Badge>
                )}
              </div>
            </div>

            <form className="space-y-4" onSubmit={(e) => void handleSaveTelegram(e)}>
              <div className="space-y-2">
                <Label htmlFor="bot-token">Токен бота</Label>
                <Input
                  id="bot-token"
                  type="password"
                  className="h-11"
                  value={botToken}
                  onChange={(e) => setBotToken(e.target.value)}
                  placeholder={telegram.bot_token_set ? '••••••••' : 'Введите токен'}
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="bot-username">{LABEL_BOT_USERNAME}</Label>
                <Input
                  id="bot-username"
                  className="h-11"
                  value={botUsername}
                  onChange={(e) => setBotUsername(e.target.value)}
                  placeholder="@mybot"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="auth-max-age">{LABEL_AUTH_MAX_AGE}</Label>
                  <Input
                    id="auth-max-age"
                    className="h-11"
                    inputMode="numeric"
                    value={authMaxAge}
                    onChange={(e) => setAuthMaxAge(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="chat-id">{LABEL_CHAT_ID}</Label>
                  <Input id="chat-id" className="h-11" value={chatId} onChange={(e) => setChatId(e.target.value)} />
                </div>
              </div>

              <div className="space-y-1 rounded-lg border bg-muted/15 p-1">
                <MiniSettingToggle
                  label="Уведомления включены"
                  checked={notifyEnabled}
                  onCheckedChange={setNotifyEnabled}
                />
                <MiniSettingToggle
                  label="Уведомлять о бэкапах"
                  checked={notifyOnBackup}
                  onCheckedChange={setNotifyOnBackup}
                />
              </div>

              {telegram.mini_app_url && (
                <div className="space-y-2">
                  <p className="text-xs font-medium text-muted-foreground">URL мини-приложения</p>
                  <CopyableValue value={telegram.mini_app_url} label="URL мини-приложения" />
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                <Button type="submit" className="gap-1.5" disabled={savingTelegram}>
                  {savingTelegram ? <Loader2 size={16} className="animate-spin" aria-hidden /> : null}
                  Сохранить
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="gap-1.5"
                  disabled={testingTelegram}
                  onClick={() => void handleTestTelegram()}
                >
                  {testingTelegram ? (
                    <Loader2 size={16} className="animate-spin" aria-hidden />
                  ) : (
                    <Send size={16} aria-hidden />
                  )}
                  Тест бота
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {refreshing && (
        <div className="tg-mini-center py-2" aria-live="polite">
          <Loader2 size={18} className="animate-spin text-muted-foreground" aria-hidden />
        </div>
      )}
    </div>
  )
}
