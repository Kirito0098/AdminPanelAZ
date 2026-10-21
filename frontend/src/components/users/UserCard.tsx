import { Suspense, lazy, useRef, useState } from 'react'
import { Activity, BarChart3, CalendarClock, KeyRound, ListChecks, UserCog } from 'lucide-react'
import { formatDate } from '@/lib/datetime'
import { formatBytes } from '@/lib/trafficFormat'
import type { UserUpdatePayload, UserProvisioningCard, UserProvisionSummary } from '@/types'
import { Badge } from '@/components/ui/badge'
import { PercentBar } from '@/components/ui/percent-bar'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import Spinner from '@/components/ui/Spinner'
import UserMetric from './UserMetric'
import UserAccessSection from './UserAccessSection'
import UserAccessControlSection from './UserAccessControlSection'
import UserConfigsSection from './UserConfigsSection'
import UserAccountSection from './UserAccountSection'

// Графики статистики тянут recharts: грузим вкладку отдельным чанком, а не вместе со страницей «Пользователи».
const UserStatsSection = lazy(() => import('./UserStatsSection'))

interface UserCardProps {
  card: UserProvisioningCard
  onSave: (id: number, data: Partial<UserUpdatePayload>) => void
  onDelete: (user: UserProvisionSummary) => void
  onRefresh: () => void
}

type BadgeVariant = 'default' | 'secondary' | 'destructive' | 'outline' | 'success' | 'warning'

const STATE_LABEL: Record<string, { label: string; variant: BadgeVariant }> = {
  unmanaged: { label: 'Без плана', variant: 'secondary' },
  pending: { label: 'Применяется', variant: 'default' },
  partial: { label: 'Требует внимания', variant: 'warning' },
  ok: { label: 'Готово', variant: 'success' },
}

export default function UserCard({ card, onSave, onDelete, onRefresh }: UserCardProps) {
  const { user } = card
  const [activeTab, setActiveTab] = useState<string>('access')
  const [planVisited, setPlanVisited] = useState(false)
  const [planDirty, setPlanDirty] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  const handleTabChange = (value: string) => {
    setActiveTab(value)
    if (value === 'plan') setPlanVisited(true)
    // Возвращаем прокрутку диалога наверх, чтобы вкладка открывалась с заголовка.
    rootRef.current?.parentElement?.scrollTo({ top: 0 })
  }

  const stateMeta = STATE_LABEL[user.provision_state ?? 'unmanaged']

  const now = new Date()
  const accessUntil = user.access_until ? new Date(user.access_until) : null
  const accessExpired = accessUntil != null && accessUntil.getTime() < now.getTime()
  const accessExpiring =
    accessUntil != null && !accessExpired && accessUntil.getTime() <= now.getTime() + 7 * 86400000
  const accessDaysLeft = accessUntil ? Math.round((accessUntil.getTime() - now.getTime()) / 86400000) : null
  const trafficLimit = user.traffic_limit_bytes ?? 0
  const trafficConsumed = user.traffic_consumed_bytes ?? 0
  const trafficPercent = trafficLimit > 0 ? Math.min((trafficConsumed / trafficLimit) * 100, 100) : 0
  const configCount = user.plan_config_indexes?.length ?? 0
  const quota = user.config_quota ?? null
  const initials = user.username.trim().slice(0, 2).toUpperCase()

  const accessLabel = !accessUntil
    ? 'Бессрочно'
    : accessExpired
      ? 'Истёк'
      : accessDaysLeft === 0
        ? 'Истекает сегодня'
        : `Осталось ${accessDaysLeft} дн.`
  const accessHint = !accessUntil
    ? 'без срока'
    : `${accessExpired ? 'истёк' : 'до'} ${formatDate(accessUntil)}`
  const accessTone = accessExpired ? 'danger' : accessExpiring ? 'warning' : 'default'
  const trafficTone = user.traffic_limit_blocked ? 'danger' : trafficPercent >= 80 ? 'warning' : 'default'

  return (
    <div ref={rootRef} className="flex flex-col">
      <div className="border-b bg-muted/20 px-4 py-4 sm:px-5">
        <div className="flex items-start gap-3">
          <span
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold uppercase text-primary"
            aria-hidden
          >
            {initials}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <h3 className="truncate text-base font-semibold leading-tight">{user.username}</h3>
              <Badge variant={user.role === 'admin' ? 'default' : 'secondary'} className="text-[10px]">
                {user.role === 'admin' ? 'Администратор' : 'Абонент'}
              </Badge>
              <Badge variant={stateMeta?.variant ?? 'secondary'} className="text-[10px]">
                {stateMeta?.label ?? user.provision_state}
              </Badge>
              {user.suspended_at && (
                <Badge variant="destructive" className="text-[10px]">
                  Приостановлен
                </Badge>
              )}
              {card.grace_hold && (
                <Badge variant="warning" className="text-[10px]">
                  Удержание {card.grace_hold.elapsed_months}/{card.grace_hold.limit_months} мес.
                </Badge>
              )}
            </div>
            <p className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-muted-foreground">
              <span>ID {user.id}</span>
              <span aria-hidden>·</span>
              <span>узлов: {user.node_ids.length}</span>
              <span aria-hidden>·</span>
              <span>конфигов: {configCount}</span>
              {user.client_base_name ? (
                <>
                  <span aria-hidden>·</span>
                  <span className="truncate font-mono">{user.client_base_name}</span>
                </>
              ) : null}
            </p>
          </div>
        </div>

        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          <UserMetric
            icon={CalendarClock}
            label="Срок доступа"
            tone={accessTone}
            value={accessLabel}
            hint={accessHint}
          />
          <UserMetric
            icon={Activity}
            label="Трафик"
            tone={trafficTone}
            value={trafficLimit > 0 ? `${Math.round(trafficPercent)}%` : 'Без лимита'}
            hint={
              trafficLimit > 0
                ? `${formatBytes(trafficConsumed)} из ${formatBytes(trafficLimit)}`
                : 'ограничений нет'
            }
          >
            {trafficLimit > 0 && (
              <PercentBar
                value={trafficConsumed}
                max={trafficLimit}
                className="h-1.5"
                barClassName={
                  user.traffic_limit_blocked
                    ? 'fill-destructive'
                    : trafficPercent >= 80
                      ? 'fill-amber-500'
                      : 'fill-primary'
                }
                label="Использование трафика"
              />
            )}
          </UserMetric>
          <UserMetric
            icon={KeyRound}
            label="Конфиги"
            value={`${configCount}${quota != null ? ` / ${quota}` : ''}`}
            hint={quota != null ? 'лимит имён' : 'без квоты'}
          />
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        <div className="sticky top-0 z-20 border-b bg-background/95 px-3 py-2 backdrop-blur sm:px-4">
          <TabsList className="h-auto w-full justify-start gap-1 overflow-x-auto bg-muted/60 p-1">
            <TabsTrigger value="access" className="gap-1.5" title="Срок доступа, пауза и лимит трафика">
              <CalendarClock size={14} aria-hidden />
              Доступ
            </TabsTrigger>
            <TabsTrigger
              value="plan"
              className="gap-1.5"
              title={planDirty ? 'Узлы, протоколы и имена конфигов · есть несохранённые изменения' : 'Узлы, протоколы и имена конфигов'}
            >
              <ListChecks size={14} aria-hidden />
              План
              {planDirty && (
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden />
              )}
            </TabsTrigger>
            <TabsTrigger value="configs" className="gap-1.5" title="Созданные конфиги и файлы">
              <KeyRound size={14} aria-hidden />
              Конфиги
            </TabsTrigger>
            <TabsTrigger value="stats" className="gap-1.5">
              <BarChart3 size={14} aria-hidden />
              Статистика
            </TabsTrigger>
            <TabsTrigger value="account" className="gap-1.5">
              <UserCog size={14} aria-hidden />
              Аккаунт
            </TabsTrigger>
          </TabsList>
        </div>

        <div className="px-4 py-4 sm:px-5">
          <TabsContent value="access" className="mt-0 space-y-4">
            <UserAccessControlSection card={card} onRefresh={onRefresh} />
          </TabsContent>
          <TabsContent
            value="plan"
            forceMount={planVisited ? true : undefined}
            className="mt-0 data-[state=inactive]:hidden"
          >
            <UserAccessSection
              card={card}
              onRefresh={onRefresh}
              onDirtyChange={setPlanDirty}
            />
          </TabsContent>
          <TabsContent value="configs" className="mt-0">
            <UserConfigsSection userId={user.id} card={card} />
          </TabsContent>
          <TabsContent value="stats" className="mt-0">
            <Suspense fallback={<Spinner label="Загрузка статистики…" className="py-8" />}>
              <UserStatsSection userId={user.id} />
            </Suspense>
          </TabsContent>
          <TabsContent value="account" className="mt-0">
            <UserAccountSection user={user} onSave={onSave} onDelete={onDelete} />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  )
}
