import { CheckCircle2, Circle, Copy, ExternalLink, LogIn, Send, Smartphone, Bot, Bell, BarChart3, ImageIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import SettingsAlert from '@/components/settings/SettingsAlert'
import TelegramBotAuthGuide from '@/components/telegram/TelegramBotAuthGuide'
import TelegramLinkedAccountsPanel from '@/components/telegram/TelegramLinkedAccountsPanel'
import TelegramMiniAppGuide from '@/components/telegram/TelegramMiniAppGuide'
import TelegramBotCommandsGuide from '@/components/telegram/TelegramBotCommandsGuide'
import TelegramRecipientsPanel from '@/components/telegram/TelegramRecipientsPanel'
import { formatDateTime } from '@/lib/datetime'
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
    <div className="flex flex-col gap-3 rounded-lg border p-4 sm:flex-row sm:items-start sm:justify-between">
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

function CopyReadonlyField({
  id,
  label,
  hint,
  value,
}: {
  id: string
  label: string
  hint: string
  value: string
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input id={id} readOnly value={value} className="w-full font-mono text-xs" placeholder="Загрузка..." />
        <Button
          type="button"
          variant="secondary"
          className="w-full shrink-0 sm:w-auto"
          disabled={!value}
          onClick={() => {
            if (value) void navigator.clipboard.writeText(value)
          }}
        >
          <Copy size={16} />
          Скопировать
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">{hint}</p>
    </div>
  )
}

function AuthMethodOption({
  active,
  title,
  description,
  onClick,
}: {
  active: boolean
  title: string
  description: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-lg border p-4 text-left transition-colors',
        active ? 'border-primary bg-primary/5 ring-1 ring-primary/30' : 'bg-muted/20 hover:bg-muted/40',
      )}
    >
      <p className="font-medium">{title}</p>
      <p className="mt-1 text-xs text-muted-foreground">{description}</p>
    </button>
  )
}

export default function TelegramSettingsPanel({ tg, activeTab, onNavigate }: TelegramSettingsPanelProps) {
  if (tg.loading) {
    return <Spinner label="Загрузка настроек..." className="py-12" />
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
              Как подключить вход через Telegram
            </CardTitle>
            <CardDescription>
              {tg.loginConfigured
                ? 'Бот настроен — на странице входа должна появиться кнопка «Войти через Telegram»'
                : 'Выполните шаги по порядку. Зелёная галочка появится, когда шаг выполнен'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <StepCard done={tg.loginConfigured} step={1} title="Создайте бота в Telegram">
              Откройте @BotFather, отправьте команду <code>/newbot</code> и следуйте подсказкам. Сохраните{' '}
              <strong>токен</strong> (длинная строка с цифрами) и <strong>имя бота</strong> (латиницей, без @).
              <Button variant="link" size="sm" className="h-auto p-0" asChild>
                <a href="https://t.me/BotFather" target="_blank" rel="noreferrer">
                  Открыть BotFather <ExternalLink className="ml-1 h-3 w-3" />
                </a>
              </Button>
            </StepCard>

            <StepCard done={tg.loginConfigured} step={2} title="Привяжите адрес панели к боту">
              В BotFather отправьте <code>/setdomain</code>, выберите своего бота и укажите адрес{' '}
              <code>{panelDomain}</code> — только домен, без <code>https://</code>.
              <Button type="button" variant="secondary" size="sm" className="mt-2" onClick={() => void copyDomain()}>
                <Copy className="mr-1.5 h-3.5 w-3.5" />
                Скопировать адрес
              </Button>
            </StepCard>

            <StepCard
              done={tg.loginConfigured}
              step={3}
              title="Вставьте токен и имя бота в панель"
              action={
                !tg.loginConfigured && onNavigate ? (
                  <Button type="button" size="sm" variant="secondary" onClick={() => onNavigate('bot')}>
                    Перейти к настройке бота
                  </Button>
                ) : undefined
              }
            >
              На вкладке «Бот и авторизация» сохраните токен, username и выберите способ входа.
            </StepCard>

            <StepCard
              done={Boolean(tg.telegramId)}
              step={4}
              title="Привяжите свой Telegram к аккаунту"
              action={
                <div className="flex flex-wrap gap-2">
                  <Button type="button" size="sm" variant="secondary" asChild>
                    <Link to="/settings/users">Настройки → Пользователи</Link>
                  </Button>
                  {onNavigate && (
                    <Button type="button" size="sm" variant="outline" onClick={() => onNavigate('interactive')}>
                      Привязать через бота
                    </Button>
                  )}
                </div>
              }
            >
              Узнайте свой числовой ID у @userinfobot или привяжите аккаунт командой <code>/link</code> в чате с
              ботом.
            </StepCard>

            <StepCard done={tg.loginConfigured && Boolean(tg.telegramId)} step={5} title="Проверьте вход">
              Откройте страницу входа и нажмите «Войти через Telegram». Панель должна работать по защищённому
              соединению (HTTPS).
              {tg.loginConfigured && (
                <Button type="button" variant="link" size="sm" className="h-auto p-0" asChild>
                  <Link to="/login">Открыть страницу входа →</Link>
                </Button>
              )}
            </StepCard>

            {!tg.loginConfigured && (
              <SettingsAlert variant="info" title="Кнопка входа не появляется?">
                Проверьте: токен и способ входа на вкладке <strong>Бот и авторизация</strong>, адрес{' '}
                <code>{panelDomain}</code> в BotFather (для legacy), модуль Telegram в{' '}
                <Link to="/settings/modules" className="font-medium text-primary underline-offset-4 hover:underline">
                  Настройки → Модули
                </Link>{' '}
                и привязку вашего Telegram ID.
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
                  Токен и имя из BotFather, способ входа через Telegram и проверка настройки
                </CardDescription>
              </div>
              <div className="flex flex-wrap gap-2">
                {tg.settings?.bot_token_set && <Badge variant="success">Токен сохранён</Badge>}
                {tg.botUsername && <Badge variant="outline">@{tg.botUsername.replace(/^@/, '')}</Badge>}
                {tg.authMethod === 'oidc' && tg.oidcLoginReady && <Badge variant="success">OIDC готов</Badge>}
                {tg.authMethod === 'legacy' && tg.legacyLoginReady && <Badge variant="success">Legacy готов</Badge>}
                {tg.authMethod === 'oidc' && !tg.oidcLoginReady && <Badge variant="warning">OIDC не завершён</Badge>}
                {tg.authMethod === 'legacy' && !tg.legacyLoginReady && (
                  <Badge variant="warning">Legacy не завершён</Badge>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <InlineProgressBar
              active={tg.saving || tg.testing}
              label={tg.testing ? 'Отправка сообщения...' : tg.saving ? 'Сохранение...' : undefined}
            />

            <TelegramBotAuthGuide
              panelDomain={panelDomain}
              authMethod={tg.authMethod}
              loginConfigured={tg.loginConfigured}
              legacyLoginReady={tg.legacyLoginReady}
              oidcLoginReady={tg.oidcLoginReady}
              botTokenSet={tg.settings?.bot_token_set}
              botUsername={tg.botUsername}
              oidcCallbackUrl={tg.settings?.oidc_callback_url}
              oidcTrustedOrigin={tg.settings?.oidc_trusted_origin}
            />

            <form onSubmit={(e) => void tg.handleSaveBot(e)} className="space-y-6">
              <div className="space-y-4">
                <p className="text-sm font-medium">Данные бота</p>
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
                    <Label htmlFor="botToken" className="shrink-0 sm:w-36 sm:pt-2">
                      Токен бота
                    </Label>
                    <div className="min-w-0 flex-1 space-y-2">
                    <Input
                      id="botToken"
                      type="password"
                      value={tg.botToken}
                      onChange={(e) => tg.setBotToken(e.target.value)}
                      placeholder={tg.settings?.bot_token_set ? '•••••••• (оставьте пустым)' : '123456:ABC...'}
                      className="w-full"
                    />
                    <p className="text-xs text-muted-foreground">
                      {tg.settings?.bot_token_set
                        ? 'Оставьте пустым, если менять не нужно'
                        : 'BotFather выдаёт его при создании бота'}
                    </p>
                    </div>
                  </div>
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
                    <Label htmlFor="botUsername" className="shrink-0 sm:w-36 sm:pt-2">
                      Имя бота (username)
                    </Label>
                    <div className="min-w-0 flex-1 space-y-2">
                    <Input
                      id="botUsername"
                      value={tg.botUsername}
                      onChange={(e) => tg.setBotUsername(e.target.value)}
                      placeholder="mybot"
                      className="w-full"
                    />
                    <p className="text-xs text-muted-foreground">Латиницей, без символа @ — как в ссылке t.me/mybot</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="space-y-6 border-t pt-6">
                <div>
                  <p className="text-sm font-medium">Вход через Telegram</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Одновременно активен только один способ — классический виджет или OpenID Connect.
                  </p>
                </div>
                <div className="space-y-2">
                  <Label>Способ входа</Label>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <AuthMethodOption
                      active={tg.authMethod === 'legacy'}
                      title="Классический виджет"
                      description="telegram.org + /setdomain в BotFather. Подходит для старых настроек бота."
                      onClick={() => tg.setAuthMethod('legacy')}
                    />
                    <AuthMethodOption
                      active={tg.authMethod === 'oidc'}
                      title="OpenID Connect"
                      description="oauth.telegram.org — рекомендуемый способ с 2025 года (PKCE + JWT)."
                      onClick={() => tg.setAuthMethod('oidc')}
                    />
                  </div>
                </div>

                {tg.authMethod === 'legacy' ? (
                  <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
                    <p className="text-sm font-medium">Настройка классического входа</p>
                    <SettingsAlert variant="info" title="BotFather: привязка домена">
                      Откройте @BotFather → ваш бот → команда <code>/setdomain</code> → укажите домен панели{' '}
                      <code>{panelDomain}</code> (без <code>https://</code>).
                    </SettingsAlert>
                    <div className="flex flex-wrap gap-2">
                      <Button type="button" variant="secondary" size="sm" onClick={() => void copyDomain()}>
                        <Copy className="mr-1.5 h-3.5 w-3.5" />
                        Скопировать домен
                      </Button>
                    </div>
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
                      <Label htmlFor="authMaxAge" className="shrink-0 sm:w-48 sm:pt-2">
                        Срок действия входа (секунды)
                      </Label>
                      <div className="min-w-0 flex-1 space-y-2">
                      <Input
                        id="authMaxAge"
                        type="number"
                        min={30}
                        max={86400}
                        value={tg.authMaxAge}
                        onChange={(e) => tg.setAuthMaxAge(e.target.value)}
                        className="w-full"
                      />
                      <p className="text-xs text-muted-foreground">
                        Сколько секунд действует кнопка «Войти через Telegram». Обычно хватает 300.
                      </p>
                      </div>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Сохраните <strong>токен</strong> и <strong>username</strong> бота выше. На странице входа
                      появится виджет telegram.org.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
                    <p className="text-sm font-medium">Настройка OpenID Connect</p>
                    <SettingsAlert variant="info" title="BotFather: Web Login">
                      @BotFather → ваш бот → <strong>Bot Settings → Web Login</strong> →{' '}
                      <strong>Switch to OpenID Connect Login</strong>. Добавьте значения ниже и скопируйте Client ID /
                      Client Secret.
                    </SettingsAlert>
                    <CopyReadonlyField
                      id="oidcRedirectUri"
                      label="Redirect URIs"
                      value={tg.settings?.oidc_callback_url || ''}
                      hint="Куда Telegram вернёт пользователя после входа. Должно совпадать символ в символ."
                    />
                    <CopyReadonlyField
                      id="oidcTrustedOrigin"
                      label="Trusted Origins"
                      value={tg.settings?.oidc_trusted_origin || ''}
                      hint="Только схема и домен (https://ваш-домен), без /login и /api."
                    />
                    {!tg.settings?.oidc_trusted_origin?.startsWith('https://') && tg.settings?.oidc_trusted_origin && (
                      <SettingsAlert variant="warning" title="Нужен HTTPS">
                        Telegram OIDC обычно не работает по HTTP. Откройте панель по <code>https://</code>.
                      </SettingsAlert>
                    )}
                    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
                        <Label htmlFor="oidcClientId" className="shrink-0 sm:w-36 sm:pt-2">
                          Client ID
                        </Label>
                        <div className="min-w-0 flex-1 space-y-2">
                        <Input
                          id="oidcClientId"
                          value={tg.oidcClientId}
                          onChange={(e) => tg.setOidcClientId(e.target.value)}
                          placeholder="123456789"
                          className="w-full"
                        />
                        <p className="text-xs text-muted-foreground">Числовой ID из BotFather → Web Login</p>
                        </div>
                      </div>
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
                        <Label htmlFor="oidcClientSecret" className="shrink-0 sm:w-36 sm:pt-2">
                          Client Secret
                        </Label>
                        <div className="min-w-0 flex-1">
                        <Input
                          id="oidcClientSecret"
                          type="password"
                          value={tg.oidcClientSecret}
                          onChange={(e) => tg.setOidcClientSecret(e.target.value)}
                          placeholder={
                            tg.settings?.oidc_client_secret_set ? '•••••••• (оставьте пустым)' : 'секрет из BotFather'
                          }
                          className="w-full"
                        />
                        </div>
                      </div>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      На странице входа будет кнопка «Войти через Telegram» через oauth.telegram.org.
                    </p>
                  </div>
                )}
              </div>

              <div className="flex flex-wrap gap-2 border-t pt-4">
                <Button type="submit" disabled={tg.saving}>
                  {tg.saving ? 'Сохранение...' : 'Сохранить'}
                </Button>
                {tg.loginConfigured && (
                  <Button type="button" variant="secondary" asChild>
                    <Link to="/login">Проверить вход</Link>
                  </Button>
                )}
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => void tg.handleTest()}
                  disabled={tg.testing || !tg.settings?.bot_token_set}
                >
                  {tg.testing ? 'Отправка...' : 'Отправить тестовое сообщение'}
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
              Приложение в Telegram
            </CardTitle>
            <CardDescription>
              Мобильная панель внутри Telegram — дашборд, конфиги и управление с телефона
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!tg.loginConfigured && (
              <SettingsAlert variant="warning" title="Сначала настройте бота">
                Сохраните токен и имя на вкладке <strong>Бот и авторизация</strong>. Убедитесь, что модуль Telegram
                включён в{' '}
                <Link to="/settings/modules" className="font-medium text-primary underline-offset-4 hover:underline">
                  Настройки → Модули
                </Link>
                .
              </SettingsAlert>
            )}

            <div className="space-y-2">
              <Label htmlFor="miniAppUrl">Ссылка на Mini App</Label>
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input
                  id="miniAppUrl"
                  readOnly
                  value={tg.settings?.mini_app_url || ''}
                  className="w-full font-mono text-xs"
                  placeholder={tg.loginConfigured ? 'Загрузка ссылки...' : 'Появится после настройки бота'}
                />
                <Button
                  type="button"
                  variant="secondary"
                  className="w-full shrink-0 sm:w-auto"
                  onClick={() => void tg.handleCopyMiniAppUrl()}
                  disabled={!tg.settings?.mini_app_url}
                >
                  <Copy size={16} />
                  Копировать
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Используйте в BotFather или оставьте автонастройку при подключении webhook на вкладке «Команды бота».
              </p>
            </div>

            <TelegramMiniAppGuide
              miniAppUrl={tg.settings?.mini_app_url}
              loginConfigured={tg.loginConfigured}
            />
          </CardContent>
        </Card>
      )}

      {activeTab === 'interactive' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Bot size={18} />
              Команды бота
            </CardTitle>
            <CardDescription>
              Интерактивный бот в личных сообщениях: команды, меню, привязка аккаунта и inline-поиск конфигов
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <InlineProgressBar
              active={tg.savingInteractive || tg.registeringWebhook || tg.deletingWebhook}
              label={
                tg.registeringWebhook
                  ? 'Подключение...'
                  : tg.deletingWebhook
                    ? 'Отключение...'
                    : tg.savingInteractive
                      ? 'Сохранение...'
                      : undefined
              }
            />

            {!tg.settings?.bot_token_set && (
              <SettingsAlert variant="warning" title="Сначала укажите токен бота">
                Заполните данные на вкладке <strong>Бот и авторизация</strong>, затем включите команды ниже.
              </SettingsAlert>
            )}

            <ToggleRow
              id="interactiveEnabled"
              label="Отвечать на команды в Telegram"
              description="Бот будет реагировать на /start, /status, /configs и другие команды"
              checked={tg.interactiveEnabled}
              disabled={tg.savingInteractive || !tg.settings?.bot_token_set}
              onCheckedChange={(checked) => void tg.handleSaveInteractive(checked)}
            />

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <div className="rounded-lg border p-3">
                <p className="text-xs text-muted-foreground">Связь с панелью</p>
                <Badge variant={tg.webhookReady ? 'success' : 'secondary'} className="mt-1">
                  {tg.webhookReady ? 'Подключено' : 'Не подключено'}
                </Badge>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-xs text-muted-foreground">Защита соединения</p>
                <p className="mt-1 text-sm font-medium">
                  {tg.settings?.webhook_secret_set ? 'Настроена' : '—'}
                </p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-xs text-muted-foreground">Последнее подключение</p>
                <p className="mt-1 text-sm font-medium">
                  {tg.settings?.webhook_set_at
                    ? formatDateTime(tg.settings.webhook_set_at)
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
                  ? 'Подключение...'
                  : tg.webhookReady
                    ? 'Переподключить'
                    : 'Подключить бота к панели'}
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={tg.deletingWebhook || !tg.webhookReady}
                onClick={() => void tg.handleDeleteWebhook()}
              >
                {tg.deletingWebhook ? 'Отключение...' : 'Отключить'}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              После подключения webhook Telegram передаёт сообщения на панель — бот отвечает в личке. Нужен HTTPS и
              доступ сервера из интернета. При ошибке «сеть недоступна» проверьте исходящий доступ сервера к
              api.telegram.org (команда на сервере: curl -4 https://api.telegram.org/).
            </p>

            <TelegramBotCommandsGuide />

            <TelegramLinkedAccountsPanel
              accounts={tg.linkedAccounts}
              unlinkingUserId={tg.unlinkingUserId}
              onUnlink={tg.handleUnlinkTelegram}
            />

            <div className="space-y-3 border-t pt-4">
              <div>
                <Label>Привязать Telegram к аккаунту</Label>
                <p className="mt-1 text-xs text-muted-foreground">
                  Получите одноразовый код и отправьте боту в личные сообщения. Код действует ограниченное время.
                </p>
              </div>
              {tg.linkCode ? (
                <div className="rounded-lg border border-dashed bg-muted/30 p-4">
                  <p className="text-xs text-muted-foreground">Отправьте боту в Telegram</p>
                  <p className="mt-1 font-mono text-lg font-semibold tracking-wide">/link {tg.linkCode}</p>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="mt-3"
                    onClick={() => void tg.handleCopyLinkCode()}
                  >
                    <Copy size={14} className="mr-1.5" />
                    Скопировать команду
                  </Button>
                </div>
              ) : (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => void tg.handleGetLinkCode()}
                  disabled={!tg.settings?.bot_token_set}
                >
                  Получить код для привязки
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
                  Уведомления
                </CardTitle>
                <CardDescription className="mt-1.5">
                  Получатели сообщений и бэкапов, типы событий и NOC-сводки
                </CardDescription>
              </div>
              {tg.notifyEnabled && (
                <Badge variant="outline">
                  {tg.notifyEventsEnabled} из {tg.adminNotify?.events.length ?? 0}
                </Badge>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {!tg.notifyEnabled && (
              <SettingsAlert variant="warning" title="Уведомления выключены" className="mb-4">
                Включите общий переключатель ниже — иначе сообщения не отправляются.
              </SettingsAlert>
            )}

            <InlineProgressBar
              active={
                tg.savingNotify ||
                tg.testingNotify ||
                tg.testingNotifyEvent !== null ||
                tg.testingNocReport !== null
              }
              label={
                tg.testingNotifyEvent
                  ? 'Отправка примера...'
                  : tg.testingNocReport === 'image'
                    ? 'Отправка изображения...'
                    : tg.testingNocReport
                      ? 'Отправка NOC...'
                      : tg.testingNotify
                        ? 'Отправка...'
                        : tg.savingNotify
                          ? 'Сохранение...'
                          : undefined
              }
            />
            <form onSubmit={(e) => void tg.handleSaveAdminNotify(e)} className="space-y-5">
              <div className="space-y-3">
                <p className="text-sm font-medium">Сообщения от бота</p>
                <ToggleRow
                  id="notifyEnabled"
                  label="Отправлять уведомления администратору"
                  description="Общий переключатель — без него события не приходят в Telegram"
                  checked={tg.notifyEnabled}
                  onCheckedChange={tg.setNotifyEnabled}
                />
                <ToggleRow
                  id="notifyOnBackup"
                  label="Присылать резервные копии в Telegram"
                  description="Архивы панели отправляются получателям, выбранным ниже"
                  checked={tg.notifyOnBackup}
                  onCheckedChange={tg.setNotifyOnBackup}
                />
              </div>

              <TelegramRecipientsPanel
                admins={tg.linkedAdmins}
                notifyRecipientIds={tg.notifyRecipientIds}
                onNotifyRecipientIdsChange={tg.setNotifyRecipientIds}
                chatIds={tg.chatIds}
                onChatIdsChange={tg.setChatIds}
              />

              <div className="space-y-3 border-t pt-4">
                <Label>О чём сообщать</Label>
                <p className="text-xs text-muted-foreground">
                  Нажмите на строку, чтобы включить или выключить событие. Кнопка{' '}
                  <Send size={12} className="inline align-text-bottom" aria-hidden /> — отправить
                  пример в Telegram.
                </p>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {tg.adminNotify?.events.map((event) => {
                    const enabled = tg.eventToggles[event.key] ?? false
                    const sending = tg.testingNotifyEvent === event.key
                    const testDisabled =
                      tg.testingNotifyEvent !== null ||
                      tg.testingNocReport !== null ||
                      tg.testingNotify ||
                      !tg.adminNotify?.bot_token_set ||
                      !tg.hasNotifyRecipients
                    return (
                      <div
                        key={event.key}
                        className={cn(
                          'flex items-start gap-2 rounded-lg border p-3 text-sm transition-colors',
                          enabled && 'border-primary/40 bg-primary/5',
                        )}
                      >
                        <button
                          type="button"
                          onClick={() =>
                            tg.setEventToggles((prev) => ({ ...prev, [event.key]: !enabled }))
                          }
                          className="flex min-w-0 flex-1 cursor-pointer items-start gap-3 text-left hover:opacity-90"
                        >
                          <Switch
                            checked={enabled}
                            tabIndex={-1}
                            aria-hidden
                            className="pointer-events-none mt-0.5"
                          />
                          <span>{event.label}</span>
                        </button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground"
                          title={`Отправить пример: ${event.label}`}
                          disabled={testDisabled}
                          onClick={() => void tg.handleTestNotifyEvent(event.key)}
                        >
                          <Send size={14} aria-hidden />
                          <span className="sr-only">{sending ? 'Отправка...' : 'Тест'}</span>
                        </Button>
                      </div>
                    )
                  })}
                </div>
              </div>

              <div className="space-y-3 rounded-lg border bg-muted/20 p-4">
                <div className="flex items-start gap-2">
                  <BarChart3 size={18} className="mt-0.5 shrink-0 text-muted-foreground" />
                  <div className="space-y-1">
                    <p className="text-sm font-medium">NOC сводка — предпросмотр</p>
                    <p className="text-xs text-muted-foreground">
                      Текстовая сводка — ежедневно или еженедельно. Еженедельный отчёт также
                      приходит одной картинкой-дашбордом (понедельник 09:00 UTC). Предпросмотр
                      отправляется выбранным получателям.
                    </p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => void tg.handleTestNocReport('daily')}
                    disabled={
                      tg.testingNocReport !== null ||
                      !tg.adminNotify?.bot_token_set ||
                      !tg.hasNotifyRecipients
                    }
                  >
                    {tg.testingNocReport === 'daily' ? 'Отправка...' : 'Ежедневная сводка'}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => void tg.handleTestNocReport('weekly')}
                    disabled={
                      tg.testingNocReport !== null ||
                      !tg.adminNotify?.bot_token_set ||
                      !tg.hasNotifyRecipients
                    }
                  >
                    {tg.testingNocReport === 'weekly' ? 'Отправка...' : 'Еженедельная сводка'}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => void tg.handleTestNocWeeklyImage()}
                    disabled={
                      tg.testingNocReport !== null ||
                      !tg.adminNotify?.bot_token_set ||
                      !tg.hasNotifyRecipients
                    }
                  >
                    {tg.testingNocReport === 'image' ? 'Отправка...' : 'Еженедельная картинка'}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                  <ImageIcon size={14} />
                  Дашборд: KPI, узлы, топ клиентов, инциденты и CIDR
                </p>
              </div>

              <div className="flex flex-wrap gap-2 border-t pt-4">
                <Button type="submit" disabled={tg.savingNotify}>
                  {tg.savingNotify ? 'Сохранение...' : 'Сохранить настройки'}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => void tg.handleTestAdminNotify()}
                  disabled={tg.testingNotify || !tg.adminNotify?.bot_token_set || !tg.hasNotifyRecipients}
                >
                  {tg.testingNotify ? 'Отправка...' : 'Проверить — отправить тест'}
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
