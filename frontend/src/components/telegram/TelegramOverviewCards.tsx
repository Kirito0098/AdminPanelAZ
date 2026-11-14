import { Bell, Bot, Send, Smartphone, UserRound } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/context/AuthContext'
import { cn } from '@/lib/utils'
import type { TelegramSection, TelegramSettingsHook } from './useTelegramSettings'

interface TelegramOverviewCardsProps {
  tg: TelegramSettingsHook
  loading?: boolean
  onNavigate: (tab: TelegramSection) => void
}

interface OverviewCard {
  title: string
  icon: LucideIcon
  value: string
  sub?: string
  accent: string
  tone?: string
}

type OverviewTabCard = OverviewCard & { tab: TelegramSection }

function OverviewCardBody({ card, loading }: { card: OverviewCard; loading: boolean }) {
  const Icon = card.icon
  return (
    <Card className={cn('h-full border-l-4 transition-colors group-hover:bg-muted/40', card.accent)}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <span className="text-sm font-semibold leading-tight">{card.title}</span>
          <div className="rounded-md bg-muted p-1.5 text-muted-foreground group-hover:text-primary">
            <Icon size={14} />
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
  )
}

export default function TelegramOverviewCards({ tg, loading = false, onNavigate }: TelegramOverviewCardsProps) {
  const { user } = useAuth()
  const profileLinked = Boolean(user && tg.linkedAccounts.some((account) => account.id === user.id))

  const authLabel =
    tg.settings?.auth_method === 'oidc'
      ? tg.oidcLoginReady
        ? 'OIDC'
        : 'OIDC · настройка'
      : tg.legacyLoginReady
        ? 'Legacy'
        : 'Legacy · настройка'

  const tabCards: OverviewTabCard[] = [
    {
      tab: 'bot',
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
      tab: 'miniapp',
      title: 'Приложение',
      icon: Smartphone,
      value: tg.miniAppReady ? 'Готово' : 'Не готово',
      sub: tg.miniAppReady ? 'Открывается в Telegram' : 'Сначала настройте бота',
      accent: tg.miniAppReady ? 'border-l-primary' : 'border-l-muted-foreground/30',
    },
    {
      tab: 'interactive',
      title: 'Команды бота',
      icon: Bot,
      value: !tg.settings?.bot_token_set
        ? '—'
        : !tg.interactiveEnabled
          ? 'Выключено'
          : !tg.commandsConnected
            ? 'Нужно подключить'
            : tg.relayError
              ? 'Узел не отвечает'
              : tg.webhookReady
                ? 'Работает'
                : 'Через узел',
      sub: tg.interactiveEnabled
        ? tg.relayEnabled
          ? '/start, /status · через узел'
          : '/start, /status и др.'
        : 'Ответы бота в чате',
      accent: tg.commandsReady
        ? 'border-l-emerald-500'
        : tg.interactiveEnabled
          ? 'border-l-amber-500'
          : 'border-l-muted-foreground/30',
      tone: tg.commandsReady ? 'text-emerald-600 dark:text-emerald-400' : undefined,
    },
    {
      tab: 'notify',
      title: 'Уведомления',
      icon: Bell,
      value: !tg.notifyEnabled ? 'Выключено' : tg.hasNotifyRecipients ? 'Включено' : 'Нет получателей',
      sub: `Событий: ${tg.notifyEventsEnabled} из ${tg.adminNotify?.events.length ?? 0}`,
      accent:
        tg.notifyEnabled && tg.hasNotifyRecipients
          ? 'border-l-emerald-500'
          : tg.notifyEnabled
            ? 'border-l-amber-500'
            : 'border-l-muted-foreground/30',
      tone:
        tg.notifyEnabled && tg.hasNotifyRecipients
          ? 'text-emerald-600 dark:text-emerald-400'
          : undefined,
    },
  ]

  const profileCard: OverviewCard = {
    title: 'Мой аккаунт',
    icon: UserRound,
    value: profileLinked ? 'Привязан' : 'Не привязан',
    sub: 'Привязать свой аккаунт — в «Моём профиле»',
    accent: profileLinked ? 'border-l-emerald-500' : 'border-l-primary',
    tone: profileLinked ? 'text-emerald-600 dark:text-emerald-400' : undefined,
  }

  const cardTriggerClassName =
    'group text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
      {tabCards.map((card) => (
        <button
          key={card.tab}
          type="button"
          onClick={() => onNavigate(card.tab)}
          className={cardTriggerClassName}
        >
          <OverviewCardBody card={card} loading={loading} />
        </button>
      ))}
      <Link to="/settings/personal" className={cardTriggerClassName}>
        <OverviewCardBody card={profileCard} loading={loading} />
      </Link>
    </div>
  )
}
