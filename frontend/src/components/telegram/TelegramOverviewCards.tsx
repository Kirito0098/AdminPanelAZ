import { Bell, Bot, LogIn, Send, Smartphone } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { TelegramSection, TelegramSettingsHook } from './useTelegramSettings'

interface TelegramOverviewCardsProps {
  tg: TelegramSettingsHook
  loading?: boolean
  onNavigate: (tab: TelegramSection) => void
}

export default function TelegramOverviewCards({ tg, loading = false, onNavigate }: TelegramOverviewCardsProps) {
  const authLabel =
    tg.settings?.auth_method === 'oidc'
      ? tg.oidcLoginReady
        ? 'OIDC'
        : 'OIDC · настройка'
      : tg.legacyLoginReady
        ? 'Legacy'
        : 'Legacy · настройка'

  const cards: Array<{
    key: TelegramSection
    title: string
    icon: typeof Send
    value: string
    sub?: string
    accent: string
    tone?: string
  }> = [
    {
      key: 'setup',
      title: 'С чего начать',
      icon: LogIn,
      value: tg.loginConfigured && tg.telegramId ? 'Готов' : tg.loginConfigured ? 'Почти готов' : 'Настроить',
      sub: tg.telegramId ? `Ваш ID: ${tg.telegramId}` : 'Пошаговая инструкция',
      accent: tg.loginConfigured && tg.telegramId ? 'border-l-emerald-500' : 'border-l-muted-foreground/30',
      tone: tg.loginConfigured && tg.telegramId ? 'text-emerald-600 dark:text-emerald-400' : undefined,
    },
    {
      key: 'bot',
      title: 'Бот и авторизация',
      icon: Send,
      value: tg.settings?.bot_token_set && tg.loginConfigured ? 'Готов' : tg.settings?.bot_token_set ? 'Почти готов' : 'Настроить',
      sub: tg.botUsername
        ? `@${tg.botUsername.replace(/^@/, '')} · ${authLabel}`
        : 'Токен, username и способ входа',
      accent: tg.settings?.bot_token_set && tg.loginConfigured ? 'border-l-emerald-500' : 'border-l-amber-500',
      tone: tg.settings?.bot_token_set && tg.loginConfigured ? 'text-emerald-600 dark:text-emerald-400' : undefined,
    },
    {
      key: 'miniapp',
      title: 'Приложение',
      icon: Smartphone,
      value: tg.miniAppReady ? 'Готово' : 'Не готово',
      sub: tg.miniAppReady ? 'Открывается в Telegram' : 'Сначала настройте бота',
      accent: tg.miniAppReady ? 'border-l-primary' : 'border-l-muted-foreground/30',
    },
    {
      key: 'interactive',
      title: 'Команды бота',
      icon: Bot,
      value: !tg.settings?.bot_token_set
        ? '—'
        : tg.interactiveEnabled
          ? tg.webhookReady
            ? 'Работает'
            : 'Нужно подключить'
          : 'Выключено',
      sub: tg.interactiveEnabled ? '/start, /status и др.' : 'Ответы бота в чате',
      accent: tg.webhookReady ? 'border-l-emerald-500' : tg.interactiveEnabled ? 'border-l-amber-500' : 'border-l-muted-foreground/30',
      tone: tg.webhookReady ? 'text-emerald-600 dark:text-emerald-400' : undefined,
    },
    {
      key: 'notify',
      title: 'Уведомления',
      icon: Bell,
      value: tg.notifyEnabled
        ? tg.notifyEventsEnabled > 0
          ? `${tg.notifyEventsEnabled} включено`
          : 'Включены'
        : 'Выключены',
      sub: tg.notifyEnabled
        ? `из ${tg.adminNotify?.events.length ?? 0} типов событий`
        : 'Сообщения от бота в личку',
      accent: tg.notifyEnabled && tg.notifyEventsEnabled > 0 ? 'border-l-sky-500' : 'border-l-muted-foreground/30',
    },
  ]

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
      {cards.map((card) => (
        <button
          key={card.key}
          type="button"
          onClick={() => onNavigate(card.key)}
          className="group text-left"
        >
          <Card
            className={cn(
              'h-full border-l-4 transition-colors hover:bg-muted/40',
              card.accent,
            )}
          >
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-2">
                <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {card.title}
                </span>
                <div className="rounded-md bg-muted p-1.5 text-muted-foreground group-hover:text-primary">
                  <card.icon size={14} />
                </div>
              </div>
              {loading ? (
                <Skeleton className="mt-2 h-7 w-20" />
              ) : (
                <div className={cn('mt-2 text-xl font-bold tracking-tight', card.tone)}>{card.value}</div>
              )}
              {card.sub && <p className="mt-1 text-xs text-muted-foreground">{card.sub}</p>}
            </CardContent>
          </Card>
        </button>
      ))}
    </div>
  )
}
