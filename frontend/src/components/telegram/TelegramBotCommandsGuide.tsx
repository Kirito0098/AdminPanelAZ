import { AlertCircle, Globe, Link2, MessageSquare, Shield, Terminal } from 'lucide-react'
import TelegramInstructionPanel from '@/components/telegram/TelegramInstructionPanel'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface CommandRow {
  command: string
  description: string
  access: 'all' | 'linked' | 'admin'
  example?: string
}

const PUBLIC_COMMANDS: CommandRow[] = [
  { command: '/start', description: 'Главное меню и клавиатура с кнопками внизу чата', access: 'all' },
  { command: '/help', description: 'Справка по командам — список зависит от вашей роли', access: 'all' },
  {
    command: '/link <код>',
    description: 'Привязка Telegram к аккаунту панели. Код получите ниже на этой вкладке',
    access: 'all',
    example: '/link a1b2c3d4',
  },
]

const USER_COMMANDS: CommandRow[] = [
  { command: '/status', description: 'Сводка панели: конфиги, online-клиенты, IP сервера', access: 'linked' },
  { command: '/myconfigs', description: 'Ваши VPN-конфиги с пагинацией и кнопками', access: 'linked' },
  { command: '/configs', description: 'Список конфигов (для admin — все, для user — свои)', access: 'linked' },
  {
    command: '/config <имя>',
    description: 'Карточка конфига: выбор протокола и отправка файлов в чат',
    access: 'linked',
    example: '/config client1',
  },
  { command: '/traffic', description: 'Трафик ваших VPN-клиентов', access: 'linked' },
]

const ADMIN_COMMANDS: CommandRow[] = [
  { command: '/settings', description: 'Настройки панели через inline-меню в чате', access: 'admin' },
  { command: '/nodes', description: 'VPN-узлы: статус, health, переключение активного', access: 'admin' },
  { command: '/cidr', description: 'Статус CIDR pipeline (если модуль маршрутизации включён)', access: 'admin' },
  { command: '/warper', description: 'Статус AZ-WARP (если модуль включён)', access: 'admin' },
]

const ACCESS_LABELS = {
  all: { label: 'Всем', variant: 'secondary' as const },
  linked: { label: 'После /link', variant: 'outline' as const },
  admin: { label: 'Admin', variant: 'default' as const },
}

function CommandTable({ title, rows }: { title: string; rows: CommandRow[] }) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</p>
      <div className="overflow-hidden rounded-lg border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
              <th className="px-3 py-2 font-medium">Команда</th>
              <th className="hidden px-3 py-2 font-medium sm:table-cell">Описание</th>
              <th className="px-3 py-2 font-medium">Доступ</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const access = ACCESS_LABELS[row.access]
              return (
                <tr key={row.command} className="border-b last:border-b-0">
                  <td className="px-3 py-2 align-top">
                    <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{row.command}</code>
                    {row.example && (
                      <p className="mt-1 font-mono text-[11px] text-muted-foreground sm:hidden">{row.example}</p>
                    )}
                    <p className="mt-1 text-xs text-muted-foreground sm:hidden">{row.description}</p>
                  </td>
                  <td className="hidden px-3 py-2 align-top text-muted-foreground sm:table-cell">
                    <p>{row.description}</p>
                    {row.example && (
                      <p className="mt-1 font-mono text-[11px]">Пример: {row.example}</p>
                    )}
                  </td>
                  <td className="px-3 py-2 align-top">
                    <Badge variant={access.variant} className="whitespace-nowrap text-[10px]">
                      {access.label}
                    </Badge>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

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

export default function TelegramBotCommandsGuide() {
  return (
    <TelegramInstructionPanel
      icon={Terminal}
      description="Как включить команды, подключить webhook и что умеет бот в личных сообщениях."
    >
      <div className="space-y-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Подключение</p>
        <GuideStep step={1} title="Сохраните токен бота">
          На вкладке <strong>Бот и авторизация</strong> укажите токен и username из @BotFather.
        </GuideStep>
        <GuideStep step={2} title="Включите команды">
          Активируйте переключатель «Отвечать на команды в Telegram» выше на этой странице.
        </GuideStep>
        <GuideStep step={3} title="Подключите webhook">
          Нажмите <strong>«Подключить бота к панели»</strong>. Telegram начнёт отправлять сообщения пользователей
          на ваш сервер — бот сможет отвечать без long polling.
        </GuideStep>
        <GuideStep step={4} title="Проверьте в Telegram">
          Откройте бота в личных сообщениях и отправьте <code>/start</code>. Должно появиться меню с кнопками внизу
          экрана.
        </GuideStep>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex gap-2 rounded-lg border bg-background/50 p-3 text-sm">
          <Globe size={16} className="mt-0.5 shrink-0 text-muted-foreground" />
          <div>
            <p className="font-medium">HTTPS и доступ из интернета</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Webhook работает только если панель открывается по <code>https://</code> и Telegram может достучаться до
              сервера (не localhost).
            </p>
          </div>
        </div>
        <div className="flex gap-2 rounded-lg border bg-background/50 p-3 text-sm">
          <Shield size={16} className="mt-0.5 shrink-0 text-muted-foreground" />
          <div>
            <p className="font-medium">Защита webhook</p>
            <p className="mt-1 text-xs text-muted-foreground">
              При подключении панель генерирует секрет — Telegram присылает его в заголовке запроса. Подделать
              сообщения без секрета нельзя.
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-3 border-t pt-4">
        <div className="flex items-center gap-2">
          <MessageSquare size={16} className="text-muted-foreground" />
          <p className="text-sm font-medium">Список команд</p>
        </div>
        <p className="text-xs text-muted-foreground">
          Команды регистрируются в BotFather автоматически при подключении webhook. Кнопки внизу чата дублируют
          основные действия.
        </p>
        <CommandTable title="Без привязки аккаунта" rows={PUBLIC_COMMANDS} />
        <CommandTable title="После привязки (/link)" rows={USER_COMMANDS} />
        <CommandTable title="Только администратор" rows={ADMIN_COMMANDS} />
      </div>

      <div className="space-y-2 border-t pt-4">
        <div className="flex items-center gap-2">
          <Link2 size={16} className="text-muted-foreground" />
          <p className="text-sm font-medium">Inline-режим</p>
        </div>
        <p className="text-sm text-muted-foreground">
          В любом чате можно написать <code>@ваш_бот имя_конфига</code> — бот предложит отправить ссылку или файл
          конфига. Работает для привязанных пользователей с доступом к конфигу.
        </p>
      </div>

      <div className="space-y-2 border-t pt-4">
        <div className="flex items-center gap-2">
          <AlertCircle size={16} className="text-muted-foreground" />
          <p className="text-sm font-medium">Если бот не отвечает</p>
        </div>
        <ul className="space-y-1.5 text-sm text-muted-foreground">
          <li className={cn('flex gap-2')}>
            <span className="text-muted-foreground/60">•</span>
            <span>
              Статус «Связь с панелью» должен быть <strong className="text-foreground">Подключено</strong> — иначе
              нажмите «Подключить» или «Переподключить».
            </span>
          </li>
          <li className="flex gap-2">
            <span className="text-muted-foreground/60">•</span>
            <span>
              Убедитесь, что модуль <strong className="text-foreground">Telegram</strong> включён в{' '}
              <strong className="text-foreground">Настройки → Модули</strong>.
            </span>
          </li>
          <li className="flex gap-2">
            <span className="text-muted-foreground/60">•</span>
            <span>
              Команды вроде <code>/status</code> требуют привязки — сначала выполните <code>/link</code> с кодом из
              блока ниже.
            </span>
          </li>
          <li className="flex gap-2">
            <span className="text-muted-foreground/60">•</span>
            <span>
              При частых запросах срабатывает rate limit — подождите минуту и повторите.
            </span>
          </li>
        </ul>
      </div>
    </TelegramInstructionPanel>
  )
}
