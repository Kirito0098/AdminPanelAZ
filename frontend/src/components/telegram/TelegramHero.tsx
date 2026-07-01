import { RefreshCw, Send } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { TelegramSettingsHook } from './useTelegramSettings'

interface TelegramHeroProps {
  tg: TelegramSettingsHook
}

function overallStatus(tg: TelegramSettingsHook) {
  if (!tg.settings?.bot_token_set) {
    return { label: 'Не настроен', variant: 'secondary' as const, dot: 'bg-muted-foreground' }
  }
  if (tg.interactiveEnabled && !tg.webhookReady) {
    return { label: 'Нужно подключить бота', variant: 'warning' as const, dot: 'bg-amber-500' }
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
    <div className="relative overflow-hidden rounded-xl border bg-gradient-to-br from-card via-card to-sky-500/5 p-5 shadow-sm">
      <div className="pointer-events-none absolute -right-10 -top-10 h-36 w-36 rounded-full bg-sky-500/10" />
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-sky-500/10 text-sky-600 dark:text-sky-400">
            <Send className="h-6 w-6" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight">Telegram</h1>
              {tg.loading ? (
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
              )}
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {botLabel ? (
                <>
                  Ваш бот: <span className="font-mono text-foreground">{botLabel}</span>
                  {tg.settings?.bot_token_set && (
                    <span className="text-muted-foreground/60"> · подключён к панели</span>
                  )}
                </>
              ) : (
                'Вход через Telegram, мобильное приложение и уведомления о событиях'
              )}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => void tg.load()} disabled={tg.loading}>
            <RefreshCw className={cn('mr-1.5 h-4 w-4', tg.loading && 'animate-spin')} />
            Обновить
          </Button>
          {tg.loginConfigured && (
            <Button variant="secondary" size="sm" asChild>
              <Link to="/login">Проверить вход</Link>
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
