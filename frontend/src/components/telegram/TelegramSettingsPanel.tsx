import { CheckCircle2, Circle, Copy, ExternalLink, LogIn, Send, Smartphone, Bot, Bell } from 'lucide-react'
import { Link } from 'react-router-dom'
import SettingsAlert from '@/components/settings/SettingsAlert'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import type { TelegramSection, TelegramSettingsHook } from './useTelegramSettings'

interface TelegramSettingsPanelProps {
  tg: TelegramSettingsHook
  activeTab: TelegramSection
  onNavigate?: (tab: TelegramSection) => void
}

function StepCard({
  done,
  step,
  title,
  children,
  action,
}: {
  done: boolean
  step: number
  title: string
  children: React.ReactNode
  action?: React.ReactNode
}) {
  return (
    <div
      className={cn(
        'flex gap-4 rounded-lg border p-4 transition-colors',
        done ? 'border-emerald-500/30 bg-emerald-500/5' : 'bg-muted/20',
      )}
    >
      <div className="flex shrink-0 flex-col items-center gap-1 pt-0.5">
        {done ? (
          <CheckCircle2 className="h-6 w-6 text-emerald-500" />
        ) : (
          <Circle className="h-6 w-6 text-muted-foreground/50" />
        )}
        <span className="text-[10px] font-medium uppercase text-muted-foreground">Шаг {step}</span>
      </div>
      <div className="min-w-0 flex-1 space-y-2">
        <p className="font-medium leading-snug">{title}</p>
        <div className="text-sm text-muted-foreground [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-xs [&_strong]:text-foreground">
          {children}
        </div>
        {action && <div className="pt-2">{action}</div>}
      </div>
    </div>
  )
}

function ToggleRow({
  id,
  label,
  description,
  checked,
  disabled,
  onCheckedChange,
}: {
  id: string
  label: string
  description?: string
  checked: boolean
  disabled?: boolean
  onCheckedChange: (checked: boolean) => void
}) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border p-4">
      <div className="min-w-0 space-y-1">
        <Label htmlFor={id} className="cursor-pointer font-medium">
          {label}
        </Label>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </div>
      <Switch id={id} checked={checked} disabled={disabled} onCheckedChange={onCheckedChange} />
    </div>
  )
}

export default function TelegramSettingsPanel({ tg, activeTab, onNavigate }: TelegramSettingsPanelProps) {
  if (tg.loading) {
    return <Spinner label="Загрузка настроек Telegram..." className="py-12" />
  }

  const panelDomain = typeof window !== 'undefined' ? window.location.hostname : 'ваш-домен.example'

  const copyDomain = async () => {
    try {
      await navigator.clipboard.writeText(panelDomain)
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="space-y-4">
      {activeTab === 'setup' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <LogIn size={18} />
              Подключение входа через Telegram
            </CardTitle>
            <CardDescription>
              {tg.loginConfigured
                ? 'Бот настроен — на /login должна появиться кнопка «Log in with Telegram»'
                : 'Пройдите шаги по порядку — статус обновится автоматически'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <StepCard done={false} step={1} title="Создайте бота в @BotFather">
              Команда <code>/newbot</code> → сохраните <strong>токен</strong> и <strong>username</strong> (без @).
              <Button variant="link" size="sm" className="h-auto p-0" asChild>
                <a href="https://t.me/BotFather" target="_blank" rel="noreferrer">
                  Открыть BotFather <ExternalLink className="ml-1 h-3 w-3" />
                </a>
              </Button>
            </StepCard>

            <StepCard done={false} step={2} title="Привяжите домен панели к боту">
              В BotFather: <code>/setdomain</code> → выберите бота → домен{' '}
              <code>{panelDomain}</code> (без https://).
              <Button type="button" variant="secondary" size="sm" className="mt-2" onClick={() => void copyDomain()}>
                <Copy className="mr-1.5 h-3.5 w-3.5" />
                Копировать домен
              </Button>
            </StepCard>

            <StepCard
              done={tg.loginConfigured}
              step={3}
              title="Сохраните токен и username в панели"
              action={
                !tg.loginConfigured && onNavigate ? (
                  <Button type="button" size="sm" variant="secondary" onClick={() => onNavigate('bot')}>
                    Перейти к настройке бота
                  </Button>
                ) : undefined
              }
            >
              Оба поля обязательны для Login Widget и Mini App.
            </StepCard>

            <StepCard
              done={Boolean(tg.telegramId)}
              step={4}
              title="Привяжите Telegram ID пользователю"
              action={
                <div className="flex flex-wrap gap-2">
                  <Button type="button" size="sm" variant="secondary" asChild>
                    <Link to="/settings">Настройки → Пользователи</Link>
                  </Button>
                  {onNavigate && (
                    <Button type="button" size="sm" variant="outline" onClick={() => onNavigate('interactive')}>
                      Код /link в боте
                    </Button>
                  )}
                </div>
              }
            >
              Числовой ID — у @userinfobot или через команду <code>/link</code> в боте.
            </StepCard>

            <StepCard done={tg.loginConfigured && Boolean(tg.telegramId)} step={5} title="Проверьте вход на /login">
              Панель должна быть доступна по HTTPS с валидным сертификатом.
              {tg.loginConfigured && (
                <Button type="button" variant="link" size="sm" className="h-auto p-0" asChild>
                  <Link to="/login">Открыть страницу входа →</Link>
                </Button>
              )}
            </StepCard>

            {!tg.loginConfigured && (
              <SettingsAlert variant="info" title="Если кнопка Telegram не появляется">
                Проверьте username и токен, домен в BotFather (<code>{panelDomain}</code>), модуль Telegram в{' '}
                <Link to="/settings" className="font-medium text-primary underline-offset-4 hover:underline">
                  Настройки → Модули
                </Link>{' '}
                и привязку Telegram ID.
              </SettingsAlert>
            )}
          </CardContent>
        </Card>
      )}

      {activeTab === 'bot' && (
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Send size={18} />
                  Бот и авторизация
                </CardTitle>
                <CardDescription className="mt-1.5">
                  Токен, username и chat_id для Login Widget, Mini App и бэкапов
                </CardDescription>
              </div>
              <div className="flex flex-wrap gap-2">
                {tg.settings?.bot_token_set && <Badge variant="success">Токен задан</Badge>}
                {tg.botUsername && <Badge variant="outline">@{tg.botUsername.replace(/^@/, '')}</Badge>}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <InlineProgressBar
              active={tg.saving || tg.testing}
              label={tg.testing ? 'Отправка сообщения...' : tg.saving ? 'Сохранение...' : undefined}
            />
            <form onSubmit={(e) => void tg.handleSave(e)} className="space-y-6">
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="botToken">Токен бота</Label>
                  <Input
                    id="botToken"
                    type="password"
                    value={tg.botToken}
                    onChange={(e) => tg.setBotToken(e.target.value)}
                    placeholder={tg.settings?.bot_token_set ? '•••••••• (оставьте пустым)' : '123456:ABC...'}
                  />
                  <p className="text-xs text-muted-foreground">
                    {tg.settings?.bot_token_set ? 'Введите новый только для замены' : 'Получите у @BotFather'}
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="botUsername">Username бота</Label>
                  <Input
                    id="botUsername"
                    value={tg.botUsername}
                    onChange={(e) => tg.setBotUsername(e.target.value)}
                    placeholder="mybot"
                  />
                  <p className="text-xs text-muted-foreground">Без @ — для Telegram Login Widget</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="authMaxAge">Макс. возраст авторизации (сек)</Label>
                  <Input
                    id="authMaxAge"
                    type="number"
                    min={30}
                    max={86400}
                    value={tg.authMaxAge}
                    onChange={(e) => tg.setAuthMaxAge(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">Рекомендуется 300</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="chatId">Chat ID (бэкапы)</Label>
                  <Input
                    id="chatId"
                    value={tg.chatId}
                    onChange={(e) => tg.setChatId(e.target.value)}
                    placeholder="-1001234567890"
                  />
                  <p className="text-xs text-muted-foreground">ID чата для архивов бэкапов</p>
                </div>
              </div>

              <div className="space-y-3 border-t pt-4">
                <p className="text-sm font-medium">Дополнительно</p>
                <ToggleRow
                  id="notifyEnabled"
                  label="Уведомления администратору (глобально)"
                  description="Master-switch для AdminNotify"
                  checked={tg.notifyEnabled}
                  onCheckedChange={tg.setNotifyEnabled}
                />
                <ToggleRow
                  id="notifyOnBackup"
                  label="Отправлять бэкапы в Telegram"
                  description="Архивы панели и client.sh 8 в chat_id"
                  checked={tg.notifyOnBackup}
                  onCheckedChange={tg.setNotifyOnBackup}
                />
              </div>

              <div className="flex flex-wrap gap-2 border-t pt-4">
                <Button type="submit" disabled={tg.saving}>
                  {tg.saving ? 'Сохранение...' : 'Сохранить'}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => void tg.handleTest()}
                  disabled={tg.testing || !tg.settings?.bot_token_set}
                >
                  {tg.testing ? 'Отправка...' : 'Тест в chat_id'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {activeTab === 'miniapp' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Smartphone size={18} />
              Telegram Mini App
            </CardTitle>
            <CardDescription>Ссылка для кнопки меню бота в BotFather</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!tg.loginConfigured && (
              <SettingsAlert variant="warning" title="Сначала настройте бота">
                Сохраните токен и username на вкладке <strong>Бот</strong>. Убедитесь, что модуль Telegram включён в{' '}
                <Link to="/settings" className="font-medium text-primary underline-offset-4 hover:underline">
                  Модули
                </Link>
                .
              </SettingsAlert>
            )}

            <div className="space-y-2">
              <Label htmlFor="miniAppUrl">URL Mini App</Label>
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input
                  id="miniAppUrl"
                  readOnly
                  value={tg.settings?.mini_app_url || ''}
                  className="font-mono text-xs"
                  placeholder={tg.loginConfigured ? 'Загрузка URL...' : 'Появится после настройки бота'}
                />
                <Button
                  type="button"
                  variant="secondary"
                  className="shrink-0"
                  onClick={() => void tg.handleCopyMiniAppUrl()}
                  disabled={!tg.settings?.mini_app_url}
                >
                  <Copy size={16} />
                  Копировать
                </Button>
              </div>
            </div>

            <div className="rounded-lg border bg-muted/30 p-4 text-sm text-muted-foreground">
              <p className="font-medium text-foreground">Настройка в BotFather</p>
              <ol className="mt-2 list-decimal space-y-1 pl-5">
                <li>
                  Команда <code>/setmenubutton</code>
                </li>
                <li>Web App → вставьте URL выше</li>
                <li>Откройте бота в Telegram и нажмите кнопку меню</li>
              </ol>
              <p className="mt-3 text-xs">Mini App работает только по HTTPS из клиента Telegram.</p>
            </div>
          </CardContent>
        </Card>
      )}

      {activeTab === 'interactive' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Bot size={18} />
              Интерактивный бот
            </CardTitle>
            <CardDescription>
              Команды /start, /status, /configs, /link и webhook для входящих сообщений
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <InlineProgressBar
              active={tg.savingInteractive || tg.registeringWebhook || tg.deletingWebhook}
              label={
                tg.registeringWebhook
                  ? 'Регистрация webhook...'
                  : tg.deletingWebhook
                    ? 'Удаление webhook...'
                    : tg.savingInteractive
                      ? 'Сохранение...'
                      : undefined
              }
            />

            {!tg.settings?.bot_token_set && (
              <SettingsAlert variant="warning" title="Нужен токен бота">
                Настройте бота на вкладке <strong>Бот</strong>, затем включите интерактивный режим.
              </SettingsAlert>
            )}

            <ToggleRow
              id="interactiveEnabled"
              label="Команды и webhook"
              description="/start, /status, /configs, /settings (admin), /cidr, /warper"
              checked={tg.interactiveEnabled}
              disabled={tg.savingInteractive || !tg.settings?.bot_token_set}
              onCheckedChange={(checked) => void tg.handleSaveInteractive(checked)}
            />

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border p-3">
                <p className="text-xs text-muted-foreground">Webhook</p>
                <Badge variant={tg.webhookReady ? 'success' : 'secondary'} className="mt-1">
                  {tg.webhookReady ? 'Зарегистрирован' : 'Не зарегистрирован'}
                </Badge>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-xs text-muted-foreground">Секрет</p>
                <p className="mt-1 text-sm font-medium">
                  {tg.settings?.webhook_secret_set ? 'Задан' : '—'}
                </p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-xs text-muted-foreground">Обновлён</p>
                <p className="mt-1 text-sm font-medium">
                  {tg.settings?.webhook_set_at
                    ? new Date(tg.settings.webhook_set_at).toLocaleString()
                    : '—'}
                </p>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                disabled={tg.registeringWebhook || !tg.interactiveEnabled || !tg.settings?.bot_token_set}
                onClick={() => void tg.handleRegisterWebhook()}
              >
                {tg.registeringWebhook
                  ? 'Регистрация...'
                  : tg.webhookReady
                    ? 'Перерегистрировать'
                    : 'Зарегистрировать webhook'}
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={tg.deletingWebhook || !tg.webhookReady}
                onClick={() => void tg.handleDeleteWebhook()}
              >
                {tg.deletingWebhook ? 'Удаление...' : 'Удалить webhook'}
              </Button>
            </div>

            <div className="space-y-3 border-t pt-4">
              <div>
                <Label>Привязка Telegram ID через бота</Label>
                <p className="mt-1 text-xs text-muted-foreground">
                  Одноразовый код → команда <code className="rounded bg-muted px-1">/link &lt;код&gt;</code> в чате с ботом
                </p>
              </div>
              {tg.linkCode ? (
                <div className="rounded-lg border border-dashed bg-muted/30 p-4">
                  <p className="text-xs text-muted-foreground">Команда для бота</p>
                  <p className="mt-1 font-mono text-lg font-semibold tracking-wide">/link {tg.linkCode}</p>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="mt-3"
                    onClick={() => void tg.handleCopyLinkCode()}
                  >
                    <Copy size={14} className="mr-1.5" />
                    Копировать
                  </Button>
                </div>
              ) : (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => void tg.handleGetLinkCode()}
                  disabled={!tg.settings?.bot_token_set}
                >
                  Получить код привязки
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {activeTab === 'notify' && (
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Bell size={18} />
                  Уведомления администратору
                </CardTitle>
                <CardDescription className="mt-1.5">
                  Per-user доставка на ваш Telegram ID
                </CardDescription>
              </div>
              {tg.notifyEnabled && (
                <Badge variant="outline">
                  {tg.notifyEventsEnabled} / {tg.adminNotify?.events.length ?? 0} событий
                </Badge>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {!tg.notifyEnabled && (
              <SettingsAlert variant="warning" title="Глобальные уведомления выключены" className="mb-4">
                Включите переключатель на вкладке <strong>Бот</strong> — иначе события не отправляются.
              </SettingsAlert>
            )}

            <InlineProgressBar
              active={tg.savingNotify || tg.testingNotify}
              label={tg.testingNotify ? 'Отправка...' : tg.savingNotify ? 'Сохранение...' : undefined}
            />
            <form onSubmit={(e) => void tg.handleSaveAdminNotify(e)} className="space-y-5">
              <div className="space-y-2 max-w-md">
                <Label htmlFor="telegramId">Ваш Telegram ID</Label>
                <Input
                  id="telegramId"
                  value={tg.telegramId}
                  onChange={(e) => tg.setTelegramId(e.target.value)}
                  placeholder="123456789"
                />
                <p className="text-xs text-muted-foreground">@userinfobot или при входе через Telegram</p>
              </div>

              <div className="space-y-3">
                <Label>Типы событий</Label>
                <div className="grid gap-2 sm:grid-cols-2">
                  {tg.adminNotify?.events.map((event) => {
                    const enabled = tg.eventToggles[event.key] ?? false
                    return (
                      <button
                        key={event.key}
                        type="button"
                        onClick={() =>
                          tg.setEventToggles((prev) => ({ ...prev, [event.key]: !enabled }))
                        }
                        className={cn(
                          'flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-left text-sm transition-colors hover:bg-muted/50',
                          enabled && 'border-primary/40 bg-primary/5',
                        )}
                      >
                        <Switch checked={enabled} tabIndex={-1} aria-hidden className="pointer-events-none mt-0.5" />
                        <span>{event.label}</span>
                      </button>
                    )
                  })}
                </div>
              </div>

              <div className="flex flex-wrap gap-2 border-t pt-4">
                <Button type="submit" disabled={tg.savingNotify}>
                  {tg.savingNotify ? 'Сохранение...' : 'Сохранить подписки'}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => void tg.handleTestAdminNotify()}
                  disabled={tg.testingNotify || !tg.adminNotify?.bot_token_set || !tg.telegramId}
                >
                  {tg.testingNotify ? 'Отправка...' : 'Тест моих уведомлений'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

export type { TelegramSection }
