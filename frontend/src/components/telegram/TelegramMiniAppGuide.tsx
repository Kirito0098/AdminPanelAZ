import { AlertCircle, Globe, Link2, Smartphone, Sparkles, Zap } from 'lucide-react'
import { Link } from 'react-router-dom'
import TelegramInstructionPanel from '@/components/telegram/TelegramInstructionPanel'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface FeatureRow {
  name: string
  user: boolean
  admin: boolean
  note?: string
}

const MINI_FEATURES: FeatureRow[] = [
  { name: 'Дашборд — сводка по конфигам и клиентам', user: true, admin: true },
  { name: 'Список VPN-конфигов, поиск и отправка файлов', user: true, admin: true },
  { name: 'Настройки уведомлений (свои)', user: true, admin: true },
  { name: 'VPN-узлы — статус и health', user: false, admin: true },
  { name: 'AZ-WARP и CIDR pipeline', user: false, admin: true, note: 'если модули включены' },
  { name: 'Часть настроек панели', user: false, admin: true },
]

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

function FeatureTable() {
  return (
    <div className="overflow-hidden rounded-lg border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
            <th className="px-3 py-2 font-medium">Раздел</th>
            <th className="px-3 py-2 font-medium text-center">User</th>
            <th className="px-3 py-2 font-medium text-center">Admin</th>
          </tr>
        </thead>
        <tbody>
          {MINI_FEATURES.map((row) => (
            <tr key={row.name} className="border-b last:border-b-0">
              <td className="px-3 py-2 align-top text-muted-foreground">
                {row.name}
                {row.note && <span className="mt-0.5 block text-[11px]">({row.note})</span>}
              </td>
              <td className="px-3 py-2 text-center align-top">
                <Badge variant={row.user ? 'success' : 'secondary'} className="text-[10px]">
                  {row.user ? 'Да' : '—'}
                </Badge>
              </td>
              <td className="px-3 py-2 text-center align-top">
                <Badge variant={row.admin ? 'success' : 'secondary'} className="text-[10px]">
                  {row.admin ? 'Да' : '—'}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export interface TelegramMiniAppGuideProps {
  miniAppUrl?: string
  loginConfigured?: boolean
}

export default function TelegramMiniAppGuide({
  miniAppUrl = '',
  loginConfigured = false,
}: TelegramMiniAppGuideProps) {
  return (
    <TelegramInstructionPanel
      icon={Smartphone}
      description="Mini App — мобильная версия панели внутри Telegram: дашборд, конфиги и управление с телефона."
    >
      {!loginConfigured && (
        <SettingsAlert variant="warning" title="Сначала настройте бота">
          Сохраните токен на вкладке <strong>Бот и авторизация</strong> — без него ссылка Mini App не появится.
        </SettingsAlert>
      )}

      <div className="space-y-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Подключение</p>
        <GuideStep step={1} title="Сохраните токен бота">
          На вкладке <strong>Бот и авторизация</strong> укажите токен и username из @BotFather. URL приложения
          формируется автоматически: <code>{miniAppUrl || 'https://ваш-домен/panel/api/tg-mini'}</code>.
          При публикации по подпути (<code>ACCESS_PATH</code>) URL включает префикс, например{' '}
          <code>/panel/api/tg-mini</code>.
        </GuideStep>
        <GuideStep step={2} title="Привяжите Telegram к аккаунту">
          В разделе <Link to="/telegram?tab=interactive">Telegram → Команды бота</Link> получите код и отправьте боту{' '}
          <code>/link &lt;код&gt;</code>. Без привязки Mini App не авторизует пользователя.
        </GuideStep>
        <GuideStep step={3} title="Откройте приложение">
          В Telegram: inline <code>@ваш_бот</code> → «AdminPanelAZ Mini App», либо кнопка на карточке конфига в боте.
        </GuideStep>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex gap-2 rounded-lg border bg-background/50 p-3 text-sm">
          <Globe size={16} className="mt-0.5 shrink-0 text-muted-foreground" />
          <div>
            <p className="font-medium">Только HTTPS</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Mini App не откроется по HTTP и не работает при прямом заходе в браузере — нужен запуск из Telegram.
            </p>
          </div>
        </div>
        <div className="flex gap-2 rounded-lg border bg-background/50 p-3 text-sm">
          <Link2 size={16} className="mt-0.5 shrink-0 text-muted-foreground" />
          <div>
            <p className="font-medium">Авторизация через initData</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Telegram передаёт подписанные данные пользователя — панель сопоставляет их с привязанным{' '}
              <code>telegram_id</code> в БД.
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-3 border-t pt-4">
        <div className="flex items-center gap-2">
          <Sparkles size={16} className="text-muted-foreground" />
          <p className="text-sm font-medium">Что доступно в приложении</p>
        </div>
        <FeatureTable />
        <p className="text-xs text-muted-foreground">
          Администратор видит дополнительные вкладки: узлы, WARP, CIDR. Обычный пользователь — дашборд, конфиги и
          свои настройки.
        </p>
      </div>

      <div className="space-y-2 border-t pt-4">
        <div className="flex items-center gap-2">
          <Zap size={16} className="text-muted-foreground" />
          <p className="text-sm font-medium">Как ещё открыть Mini App</p>
        </div>
        <ul className="space-y-1.5 text-sm text-muted-foreground">
          <li className="flex gap-2">
            <span className="text-muted-foreground/60">•</span>
            <span>
              Inline: в любом чате <code>@ваш_бот</code> → подсказка «AdminPanelAZ Mini App».
            </span>
          </li>
          <li className="flex gap-2">
            <span className="text-muted-foreground/60">•</span>
            <span>
              Отправка конфига из бота — кнопка «Открыть в Mini App» на карточке клиента.
            </span>
          </li>
        </ul>
      </div>

      <div className="space-y-2 border-t pt-4">
        <div className="flex items-center gap-2">
          <AlertCircle size={16} className="text-muted-foreground" />
          <p className="text-sm font-medium">Если приложение не открывается</p>
        </div>
        <ul className="space-y-1.5 text-sm text-muted-foreground">
          <li className={cn('flex gap-2')}>
            <span className="text-muted-foreground/60">•</span>
            <span>
              Открывайте <strong className="text-foreground">из Telegram</strong>, а не по прямой ссылке в Chrome/Safari.
            </span>
          </li>
          <li className="flex gap-2">
            <span className="text-muted-foreground/60">•</span>
            <span>
              Проверьте привязку: <code>/link</code> на вкладке «Команды бота» или Telegram ID в{' '}
              <Link to="/settings" className="font-medium text-primary underline-offset-4 hover:underline">
                Настройки → Пользователи
              </Link>
              .
            </span>
          </li>
          <li className="flex gap-2">
            <span className="text-muted-foreground/60">•</span>
            <span>
              URL в BotFather должен совпадать с полем выше <strong className="text-foreground">символ в символ</strong>
              {miniAppUrl ? (
                <>
                  : <code className="rounded bg-muted px-1 text-xs">{miniAppUrl}</code>
                </>
              ) : (
                '.'
              )}
            </span>
          </li>
          <li className="flex gap-2">
            <span className="text-muted-foreground/60">•</span>
            <span>
              Убедитесь, что модуль <strong className="text-foreground">Telegram</strong> включён и фронт Mini App
              собран (<code>npm run build:tg-mini</code> на сервере при установке).
            </span>
          </li>
        </ul>
      </div>
    </TelegramInstructionPanel>
  )
}
