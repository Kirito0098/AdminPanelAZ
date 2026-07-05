import { AlertCircle, Bot, Globe, KeyRound, Send, Shield } from 'lucide-react'
import { Link } from 'react-router-dom'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import TelegramInstructionPanel from '@/components/telegram/TelegramInstructionPanel'
import type { TelegramAuthMethod } from './useTelegramSettings'

function GuideStep({
  step,
  title,
  children,
}: {
  step: number
  title: string
  children: React.ReactNode
}) {
  return (
    <div className="flex gap-3">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
        {step}
      </div>
      <div className="min-w-0 space-y-1">
        <p className="font-medium leading-snug">{title}</p>
        <div className="text-sm text-muted-foreground [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-xs [&_strong]:text-foreground">
          {children}
        </div>
      </div>
    </div>
  )
}

export interface TelegramBotAuthGuideProps {
  panelDomain: string
  authMethod: TelegramAuthMethod
  loginConfigured?: boolean
  legacyLoginReady?: boolean
  oidcLoginReady?: boolean
  botTokenSet?: boolean
  botUsername?: string
  oidcCallbackUrl?: string
  oidcTrustedOrigin?: string
}

export default function TelegramBotAuthGuide({
  panelDomain,
  authMethod,
  loginConfigured = false,
  legacyLoginReady = false,
  oidcLoginReady = false,
  botTokenSet = false,
  botUsername = '',
  oidcCallbackUrl = '',
  oidcTrustedOrigin = '',
}: TelegramBotAuthGuideProps) {
  const authReady = authMethod === 'oidc' ? oidcLoginReady : legacyLoginReady

  return (
    <TelegramInstructionPanel
      icon={Send}
      description="Токен и username бота — основа для входа, команд, Mini App и уведомлений в Telegram."
    >
      <div className="space-y-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">С чего начать</p>
        <GuideStep step={1} title="Создайте бота в @BotFather">
          Команда <code>/newbot</code> → сохраните <strong>токен</strong> и <strong>username</strong> (латиницей, без
          @). Эти же данные вставьте в форму ниже.
        </GuideStep>
        <GuideStep step={2} title="Включите модуль Telegram">
          В{' '}
          <Link to="/settings" className="font-medium text-primary underline-offset-4 hover:underline">
            Настройки → Модули
          </Link>{' '}
          должен быть активен модуль <strong>Telegram</strong> — иначе вход и бот не работают.
        </GuideStep>
        <GuideStep step={3} title="Выберите способ входа">
          <strong>Legacy</strong> — виджет telegram.org, нужен <code>/setdomain</code>.{' '}
          <strong>OpenID Connect</strong> — рекомендуемый способ (oauth.telegram.org, PKCE + JWT). Активен только
          один метод.
        </GuideStep>
        <GuideStep step={4} title="Настройте BotFather под выбранный метод">
          {authMethod === 'legacy' ? (
            <>
              <code>/setdomain</code> → домен <code>{panelDomain}</code> (без <code>https://</code>). Затем сохраните
              токен, username и нажмите <strong>Сохранить</strong>.
            </>
          ) : (
            <>
              Bot Settings → Web Login → Switch to OpenID Connect. Добавьте Redirect URI и Trusted Origin из формы
              ниже, скопируйте Client ID / Secret в панель.
            </>
          )}
        </GuideStep>
        <GuideStep step={5} title="Привяжите Telegram ID администратора">
          Вход через Telegram сработает только если у пользователя панели указан{' '}
          <code>telegram_id</code> — через{' '}
          <Link to="/telegram?tab=interactive" className="font-medium text-primary underline-offset-4 hover:underline">
            /link в боте
          </Link>{' '}
          или в «Настройки → Пользователи».
        </GuideStep>
        <GuideStep step={6} title="Проверьте вход">
          Откройте <Link to="/login">страницу входа</Link> → «Войти через Telegram». Нужен HTTPS.
        </GuideStep>
      </div>

      <div className="overflow-hidden rounded-lg border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
              <th className="px-3 py-2 font-medium">Параметр</th>
              <th className="px-3 py-2 font-medium">Legacy</th>
              <th className="px-3 py-2 font-medium">OpenID Connect</th>
            </tr>
          </thead>
          <tbody className="text-muted-foreground">
            <tr className="border-b">
              <td className="px-3 py-2 align-top font-medium text-foreground">Где настраивается</td>
              <td className="px-3 py-2 align-top">BotFather → /setdomain</td>
              <td className="px-3 py-2 align-top">BotFather → Web Login → OIDC</td>
            </tr>
            <tr className="border-b">
              <td className="px-3 py-2 align-top font-medium text-foreground">Кнопка на /login</td>
              <td className="px-3 py-2 align-top">Виджет telegram.org</td>
              <td className="px-3 py-2 align-top">Редирект oauth.telegram.org</td>
            </tr>
            <tr className="border-b">
              <td className="px-3 py-2 align-top font-medium text-foreground">Нужен HTTPS</td>
              <td className="px-3 py-2 align-top">Желательно</td>
              <td className="px-3 py-2 align-top">
                <Badge variant="warning" className="text-[10px]">
                  Обязательно
                </Badge>
              </td>
            </tr>
            <tr className="border-b">
              <td className="px-3 py-2 align-top font-medium text-foreground">Доп. поля в панели</td>
              <td className="px-3 py-2 align-top">Срок действия входа (сек)</td>
              <td className="px-3 py-2 align-top">Client ID, Client Secret</td>
            </tr>
            <tr>
              <td className="px-3 py-2 align-top font-medium text-foreground">Когда выбирать</td>
              <td className="px-3 py-2 align-top">Старые боты, простая настройка</td>
              <td className="px-3 py-2 align-top">Новые установки с 2025 г.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex gap-2 rounded-lg border bg-background/50 p-3 text-sm">
          <Bot size={16} className="mt-0.5 shrink-0 text-muted-foreground" />
          <div>
            <p className="font-medium">Токен используется везде</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Один бот — для входа, webhook-команд, Mini App, уведомлений и отправки бэкапов. Username нужен для
              виджета legacy и ссылок <code>t.me/…</code>.
            </p>
          </div>
        </div>
        <div className="flex gap-2 rounded-lg border bg-background/50 p-3 text-sm">
          <KeyRound size={16} className="mt-0.5 shrink-0 text-muted-foreground" />
          <div>
            <p className="font-medium">Статус настройки</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Badge variant={botTokenSet ? 'success' : 'secondary'} className="text-[10px]">
                {botTokenSet ? 'Токен ✓' : 'Нет токена'}
              </Badge>
              <Badge variant={botUsername ? 'outline' : 'secondary'} className="text-[10px]">
                {botUsername ? `@${botUsername.replace(/^@/, '')}` : 'Нет username'}
              </Badge>
              <Badge variant={authReady ? 'success' : 'warning'} className="text-[10px]">
                {authMethod === 'oidc' ? 'OIDC' : 'Legacy'} {authReady ? '✓' : '…'}
              </Badge>
            </div>
          </div>
        </div>
      </div>

      {authMethod === 'oidc' && (oidcCallbackUrl || oidcTrustedOrigin) && (
        <div className="space-y-2 rounded-lg border border-dashed bg-background/40 p-3">
          <p className="text-xs font-medium">Значения для BotFather → Web Login</p>
          {oidcCallbackUrl && (
            <p className="font-mono text-[11px] text-muted-foreground break-all">
              Redirect: <span className="text-foreground">{oidcCallbackUrl}</span>
            </p>
          )}
          {oidcTrustedOrigin && (
            <p className="font-mono text-[11px] text-muted-foreground break-all">
              Origin: <span className="text-foreground">{oidcTrustedOrigin}</span>
            </p>
          )}
        </div>
      )}

      {authMethod === 'legacy' && (
        <SettingsAlert variant="info" title="Legacy: домен панели">
          В BotFather укажите <code>{panelDomain}</code> — только домен, без пути и без <code>https://</code>.
        </SettingsAlert>
      )}

      <div className="space-y-2 border-t pt-4">
        <div className="flex items-center gap-2">
          <Globe size={16} className="text-muted-foreground" />
          <p className="text-sm font-medium">Что включается после сохранения бота</p>
        </div>
        <ul className="space-y-1.5 text-sm text-muted-foreground">
          <li className="flex gap-2">
            <span className="text-muted-foreground/60">•</span>
            <span>
              <Link to="/telegram?tab=interactive" className="font-medium text-primary underline-offset-4 hover:underline">
                Команды бота
              </Link>{' '}
              — webhook, /start, /link и другие команды.
            </span>
          </li>
          <li className="flex gap-2">
            <span className="text-muted-foreground/60">•</span>
            <span>
              <Link to="/telegram?tab=miniapp" className="font-medium text-primary underline-offset-4 hover:underline">
                Mini App
              </Link>{' '}
              — мобильная панель по URL <code>/api/tg-mini</code>.
            </span>
          </li>
          <li className="flex gap-2">
            <span className="text-muted-foreground/60">•</span>
            <span>
              <Link to="/telegram?tab=notify" className="font-medium text-primary underline-offset-4 hover:underline">
                Уведомления
              </Link>{' '}
              — алерты и бэкапы в Telegram.
            </span>
          </li>
        </ul>
      </div>

      <div className="space-y-2 border-t pt-4">
        <div className="flex items-center gap-2">
          <AlertCircle size={16} className="text-muted-foreground" />
          <p className="text-sm font-medium">Если вход не работает</p>
        </div>
        <ul className="space-y-1.5 text-sm text-muted-foreground">
          <li className={cn('flex gap-2')}>
            <span className="text-muted-foreground/60">•</span>
            <span>
              На странице входа нет кнопки — проверьте модуль Telegram, сохранённый токен и завершённость настройки{' '}
              {authMethod === 'oidc' ? 'OIDC (Client ID + Secret)' : 'legacy (домен + username)'}.
            </span>
          </li>
          <li className="flex gap-2">
            <span className="text-muted-foreground/60">•</span>
            <span>
              Кнопка есть, но «Пользователь не найден» — у аккаунта панели нет привязанного Telegram ID с тем же
              числом, что у вашего Telegram.
            </span>
          </li>
          <li className="flex gap-2">
            <span className="text-muted-foreground/60">•</span>
            <span>
              OIDC: Redirect URI и Trusted Origin в BotFather должны совпадать с полями формы{' '}
              <strong className="text-foreground">символ в символ</strong>.
            </span>
          </li>
          <li className="flex gap-2">
            <span className="text-muted-foreground/60">•</span>
            <span>
              Legacy: виджет не грузится — проверьте <code>/setdomain</code> и что username бота совпадает с BotFather.
            </span>
          </li>
          {!loginConfigured && (
            <li className="flex gap-2">
              <span className="text-muted-foreground/60">•</span>
              <span>
                «Тестовое сообщение» проверяет только токен и получателей бэкапов — для входа нужна отдельная настройка
                авторизации выше.
              </span>
            </li>
          )}
        </ul>
      </div>

      <div className="flex gap-2 rounded-lg border bg-background/50 p-3 text-sm">
        <Shield size={16} className="mt-0.5 shrink-0 text-muted-foreground" />
        <p className="text-xs text-muted-foreground">
          Токен бота и Client Secret — секреты. Не публикуйте их и не коммитьте в git. При утечке перевыпустите в
          BotFather.
        </p>
      </div>
    </TelegramInstructionPanel>
  )
}
