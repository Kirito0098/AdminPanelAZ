import { RefreshCw, Send } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import PageSectionHeader from '@/components/shared/PageSectionHeader'
import { DOCS } from '@/lib/docsUrls'
import { cn } from '@/lib/utils'
import type { TelegramSettingsHook } from './useTelegramSettings'

interface TelegramHeroProps {
  tg: TelegramSettingsHook
}

function overallStatus(tg: TelegramSettingsHook) {
  if (!tg.settings?.bot_token_set) {
    return { label: 'Не настроен', variant: 'secondary' as const, dot: 'bg-muted-foreground' }
  }
  if (tg.interactiveEnabled && !tg.commandsConnected) {
    return { label: 'Нужно подключить бота', variant: 'warning' as const, dot: 'bg-amber-500' }
  }
  if (tg.interactiveEnabled && tg.relayError) {
    return { label: 'Узел не отвечает', variant: 'warning' as const, dot: 'bg-amber-500' }
  }
  if (tg.loginConfigured) {
    return { label: 'Всё работает', variant: 'success' as const, dot: 'bg-emerald-500' }
  }
  return { label: 'Настройка не завершена', variant: 'warning' as const, dot: 'bg-amber-500' }
}

export default function TelegramHero({ tg }: TelegramHeroProps) {
  const status = overallStatus(tg)
  const botLabel = tg.botUsername ? `@${tg.botUsername.replace(/^@/, '')}` : null

  return (
    <PageSectionHeader
      card
      icon={Send}
      title="Telegram"
      iconClassName="bg-sky-500/10 text-sky-600 dark:text-sky-400"
      titleAddon={
        tg.loading ? (
          <Skeleton className="h-6 w-24 rounded-full" />
        ) : (
          <Badge variant={status.variant} className="gap-1.5">
            <span
              className={cn(
                'h-2 w-2 rounded-full',
                status.dot,
                status.variant === 'success' && 'animate-pulse',
              )}
            />
            {status.label}
          </Badge>
        )
      }
      description={
        botLabel ? (
          <>
            Ваш бот: <span className="font-mono text-foreground">{botLabel}</span>
            {tg.settings?.bot_token_set && (
              <span className="text-muted-foreground/60">
                {' '}
                · {tg.relayEnabled ? 'связь с Telegram через узел' : 'подключён к панели'}
              </span>
            )}
          </>
        ) : (
          'Вход через Telegram, мобильное приложение и уведомления о событиях'
        )
      }
      docsHref={DOCS.telegram}
      actions={
        <>
          <Button variant="outline" size="sm" onClick={() => void tg.load()} disabled={tg.loading}>
            <RefreshCw className={cn('mr-1.5 h-4 w-4', tg.loading && 'animate-spin')} />
            Обновить
          </Button>
          {tg.loginConfigured && (
            <Button variant="secondary" size="sm" asChild>
              <Link to="/login">Проверить вход</Link>
            </Button>
          )}
        </>
      }
    />
  )
}
