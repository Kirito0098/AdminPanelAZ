import { CheckCircle2, Circle, Copy, ExternalLink, LogIn, Send, Smartphone, Bot, Bell, BarChart3, ImageIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import SettingsAlert from '@/components/settings/SettingsAlert'
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
                    Перейти к данным бота
                  </Button>
                ) : undefined
              }
            >
              На вкладке «Данные бота» вставьте токен и имя — они нужны для входа и приложения в Telegram.
            </StepCard>

            <StepCard
              done={Boolean(tg.telegramId)}
              step={4}
              title="Привяжите свой Telegram к аккаунту"
              action={
                <div className="flex flex-wrap gap-2">
                  <Button type="button" size="sm" variant="secondary" asChild>
                    <Link to="/settings">Настройки → Пользователи</Link>
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
                Проверьте: имя и токен бота, адрес <code>{panelDomain}</code> в BotFather, модуль Telegram в{' '}
                <Link to="/settings" className="font-medium text-primary underline-offset-4 hover:underline">
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
                  Данные бота
                </CardTitle>
                <CardDescription className="mt-1.5">
                  Токен и имя из BotFather — нужны для входа, приложения и отправки сообщений
                </CardDescription>
              </div>
              <div className="flex flex-wrap gap-2">
                {tg.settings?.bot_token_set && <Badge variant="success">Токен сохранён</Badge>}
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
                    {tg.settings?.bot_token_set
                      ? 'Оставьте пустым, если менять не нужно'
                      : 'BotFather выдаёт его при создании бота'}
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="botUsername">Имя бота (username)</Label>
                  <Input
                    id="botUsername"
                    value={tg.botUsername}
                    onChange={(e) => tg.setBotUsername(e.target.value)}
                    placeholder="mybot"
                  />
                  <p className="text-xs text-muted-foreground">Латиницей, без символа @ — как в ссылке t.me/mybot</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="authMaxAge">Срок действия входа (секунды)</Label>
                  <Input
                    id="authMaxAge"
                    type="number"
                    min={30}
                    max={86400}
                    value={tg.authMaxAge}
                    onChange={(e) => tg.setAuthMaxAge(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">Сколько секунд действует кнопка «Войти через Telegram». Обычно хватает 300</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="chatId">ID чата для резервных копий</Label>
                  <Input
                    id="chatId"
                    value={tg.chatId}
                    onChange={(e) => tg.setChatId(e.target.value)}
                    placeholder="-1001234567890"
                  />
                  <p className="text-xs text-muted-foreground">Сюда бот будет присылать архивы бэкапов (личный чат или группа)</p>
                </div>
              </div>

              <div className="space-y-3 border-t pt-4">
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
                  description="Архивы панели отправляются в указанный ID чата"
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
              Панель открывается прямо в Telegram — удобно с телефона
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!tg.loginConfigured && (
              <SettingsAlert variant="warning" title="Сначала настройте бота">
                Сохраните токен и имя на вкладке <strong>Данные бота</strong>. Убедитесь, что модуль Telegram
                включён в{' '}
                <Link to="/settings" className="font-medium text-primary underline-offset-4 hover:underline">
                  Настройки → Модули
                </Link>
                .
              </SettingsAlert>
            )}

            <div className="space-y-2">
              <Label htmlFor="miniAppUrl">Ссылка на приложение</Label>
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input
                  id="miniAppUrl"
                  readOnly
                  value={tg.settings?.mini_app_url || ''}
                  className="font-mono text-xs"
                  placeholder={tg.loginConfigured ? 'Загрузка ссылки...' : 'Появится после настройки бота'}
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
              <p className="text-xs text-muted-foreground">Эту ссылку нужно вставить в BotFather — см. инструкцию ниже</p>
            </div>

            <div className="rounded-lg border bg-muted/30 p-4 text-sm text-muted-foreground">
              <p className="font-medium text-foreground">Как добавить кнопку в бота</p>
              <ol className="mt-2 list-decimal space-y-1 pl-5">
                <li>
                  В BotFather отправьте <code>/setmenubutton</code>
                </li>
                <li>Выберите своего бота → Web App → вставьте ссылку выше</li>
                <li>Откройте бота в Telegram и нажмите кнопку меню внизу экрана</li>
              </ol>
              <p className="mt-3 text-xs">Приложение работает только при открытии из Telegram и по защищённому соединению (HTTPS).</p>
            </div>
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
              Бот отвечает в чате на команды вроде /start, /status и /link
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
                Заполните данные на вкладке <strong>Данные бота</strong>, затем включите команды ниже.
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

            <div className="grid gap-3 sm:grid-cols-3">
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
              Для работы команд панель должна быть доступна из интернета по HTTPS.
            </p>

            <div className="space-y-3 border-t pt-4">
              <div>
                <Label>Привязать Telegram к аккаунту через бота</Label>
                <p className="mt-1 text-xs text-muted-foreground">
                  Получите код ниже и отправьте боту команду <code className="rounded bg-muted px-1">/link &lt;код&gt;</code>
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
                  Выберите, о каких событиях бот будет писать вам в личные сообщения
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
                Включите общий переключатель на вкладке <strong>Данные бота</strong> — иначе сообщения не
                отправляются.
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
              <div className="space-y-2 max-w-md">
                <Label htmlFor="telegramId">Ваш Telegram ID</Label>
                <Input
                  id="telegramId"
                  value={tg.telegramId}
                  onChange={(e) => tg.setTelegramId(e.target.value)}
                  placeholder="123456789"
                />
                <p className="text-xs text-muted-foreground">
                  Узнайте у @userinfobot или при входе через Telegram — это число из цифр
                </p>
              </div>

              <div className="space-y-3">
                <Label>О чём сообщать</Label>
                <p className="text-xs text-muted-foreground">
                  Нажмите на строку, чтобы включить или выключить событие. Кнопка{' '}
                  <Send size={12} className="inline align-text-bottom" aria-hidden /> — отправить
                  пример в Telegram.
                </p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {tg.adminNotify?.events.map((event) => {
                    const enabled = tg.eventToggles[event.key] ?? false
                    const sending = tg.testingNotifyEvent === event.key
                    const testDisabled =
                      tg.testingNotifyEvent !== null ||
                      tg.testingNocReport !== null ||
                      tg.testingNotify ||
                      !tg.adminNotify?.bot_token_set ||
                      !tg.telegramId
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
                      приходит только вам.
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
                      !tg.telegramId
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
                      !tg.telegramId
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
                      !tg.telegramId
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
                  disabled={tg.testingNotify || !tg.adminNotify?.bot_token_set || !tg.telegramId}
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
