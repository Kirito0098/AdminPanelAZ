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
      key: 'bot',
      title: 'Бот',
      icon: Send,
      value: tg.loginConfigured ? 'Готов' : tg.settings?.bot_token_set ? 'Частично' : 'Не задан',
      sub: tg.botUsername ? `@${tg.botUsername.replace(/^@/, '')}` : 'Токен и username',
      accent: tg.loginConfigured ? 'border-l-emerald-500' : 'border-l-amber-500',
      tone: tg.loginConfigured ? 'text-emerald-600 dark:text-emerald-400' : undefined,
    },
    {
      key: 'miniapp',
      title: 'Mini App',
      icon: Smartphone,
      value: tg.miniAppReady ? 'URL готов' : '—',
      sub: tg.miniAppReady ? 'HTTPS из Telegram' : 'Нужен токен бота',
      accent: tg.miniAppReady ? 'border-l-primary' : 'border-l-muted-foreground/30',
    },
    {
      key: 'interactive',
      title: 'Webhook',
      icon: Bot,
      value: !tg.settings?.bot_token_set
        ? '—'
        : tg.interactiveEnabled
          ? tg.webhookReady
            ? 'Активен'
            : 'Не зарег.'
          : 'Выключен',
      sub: tg.interactiveEnabled ? 'Команды бота' : 'Интерактив выкл.',
      accent: tg.webhookReady ? 'border-l-emerald-500' : tg.interactiveEnabled ? 'border-l-amber-500' : 'border-l-muted-foreground/30',
      tone: tg.webhookReady ? 'text-emerald-600 dark:text-emerald-400' : undefined,
    },
    {
      key: 'notify',
      title: 'Уведомления',
      icon: Bell,
      value: tg.notifyEnabled ? String(tg.notifyEventsEnabled) : 'Выкл.',
      sub: tg.notifyEnabled
        ? `из ${tg.adminNotify?.events.length ?? 0} событий`
        : 'Глобально выключены',
      accent: tg.notifyEnabled && tg.notifyEventsEnabled > 0 ? 'border-l-sky-500' : 'border-l-muted-foreground/30',
    },
    {
      key: 'setup',
      title: 'Вход',
      icon: LogIn,
      value: tg.loginConfigured ? 'Доступен' : 'Настроить',
      sub: tg.telegramId ? `ID: ${tg.telegramId}` : 'Привязка Telegram ID',
      accent: tg.loginConfigured && tg.telegramId ? 'border-l-emerald-500' : 'border-l-muted-foreground/30',
      tone: tg.loginConfigured ? 'text-emerald-600 dark:text-emerald-400' : undefined,
    },
  ]

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
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
