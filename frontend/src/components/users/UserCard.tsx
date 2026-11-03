import { Suspense, lazy, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Activity,
  CalendarClock,
  History,
  KeyRound,
  MessageSquare,
  Settings,
  StickyNote,
  UserCog,
} from 'lucide-react'
import { formatDate } from '@/lib/datetime'
import { formatBytes } from '@/lib/trafficFormat'
import type { UserUpdatePayload, UserProvisioningCard, UserProvisionSummary } from '@/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { PercentBar } from '@/components/ui/percent-bar'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import Spinner from '@/components/ui/Spinner'
import UserMetric from './UserMetric'
import UserAccessControlSection from './UserAccessControlSection'
import UserTrafficSection from './UserTrafficSection'
import UserConfigsSection from './UserConfigsSection'
import UserRightsSection from './UserRightsSection'
import UserAccountSection from './UserAccountSection'
import ChatThread from '@/components/messages/ChatThread'
import { getUserUnreadCount } from '@/api/messages'
import { useFeatureModules } from '@/context/FeatureModulesContext'

// История грузится отдельным чанком: в карточке она нужна редко.
const UserHistorySection = lazy(() => import('./UserHistorySection'))

interface UserCardProps {
  card: UserProvisioningCard
  onSave: (id: number, data: Partial<UserUpdatePayload>, message?: string) => void
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
  const rootRef = useRef<HTMLDivElement>(null)
  const { isEnabled } = useFeatureModules()
  // Чат доступен только привязанным абонентам и только при включённом модуле.
  const chatEnabled = isEnabled('user_messaging') && Boolean(user.telegram_id)
  const rightsVisible = user.role === 'user'
  const [chatUnread, setChatUnread] = useState(0)
  const [planDirty, setPlanDirty] = useState(false)
  const [searchParams, setSearchParams] = useSearchParams()

  const allowedTabs = useMemo(() => {
    const tabs = ['access', 'traffic', 'configs']
    if (rightsVisible) tabs.push('rights')
    tabs.push('account', 'history')
    if (chatEnabled) tabs.push('chat')
    return new Set(tabs)
  }, [rightsVisible, chatEnabled])

  // Deep-link ?tab=traffic — чтобы ссылкой можно было открыть нужную вкладку.
  const [activeTab, setActiveTab] = useState<string>(() => {
    const requested = searchParams.get('tab')
    return requested && allowedTabs.has(requested) ? requested : 'access'
  })

  useEffect(() => {
    if (!chatEnabled) return
    let cancelled = false
    getUserUnreadCount(user.id)
      .then(({ count }) => {
        if (!cancelled) setChatUnread(count)
      })
      .catch(() => {
        // Бейдж не критичен: вкладка «Чат» работает и без него.
      })
    return () => {
      cancelled = true
    }
  }, [chatEnabled, user.id])

  const handleTabChange = (value: string) => {
    setActiveTab(value)
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('tab', value)
        return next
      },
      { replace: true },
    )
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
  // Без плана имена и база берутся из фактических конфигов владельца.
  const baseName = user.client_base_name ?? user.owned_config_base_name ?? null
  const configCount = card.has_plan ? (user.plan_config_indexes?.length ?? 0) : card.configs.length
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
              {user.online && (
                <Badge variant="success" className="text-[10px]" title="Есть активная VPN-сессия">
                  Онлайн
                </Badge>
              )}
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
              {baseName ? (
                <>
                  <span aria-hidden>·</span>
                  <span className="truncate font-mono">{baseName}</span>
                </>
              ) : null}
            </p>
            {user.note && user.note.trim() ? (
              <p
                className="mt-1.5 flex items-start gap-1.5 rounded-md border border-amber-500/25 bg-amber-500/10 px-2 py-1 text-xs leading-snug text-amber-900 dark:text-amber-200"
                title={user.note}
              >
                <StickyNote size={12} className="mt-0.5 shrink-0 opacity-70" aria-hidden />
                <span className="line-clamp-2 [overflow-wrap:anywhere]">{user.note.trim()}</span>
              </p>
            ) : null}
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
        <div className="sticky top-14 z-20 border-b bg-background/95 px-3 py-2 backdrop-blur sm:px-4">
          <div className="flex items-center gap-2">
            <TabsList className="h-auto min-w-0 flex-1 justify-start gap-1 overflow-x-auto bg-muted/60 p-1">
              <TabsTrigger value="access" className="gap-1.5" title="Срок доступа, пауза и ключ продления">
                <CalendarClock size={14} aria-hidden />
                Доступ
              </TabsTrigger>
              <TabsTrigger value="traffic" className="gap-1.5" title="Лимит трафика и графики расхода">
                <Activity size={14} aria-hidden />
                Трафик
              </TabsTrigger>
              <TabsTrigger
                value="configs"
                className="gap-1.5"
                title={
                  planDirty
                    ? 'Конфиги и план · есть несохранённые изменения'
                    : 'Выданные конфиги и план'
                }
              >
                <KeyRound size={14} aria-hidden />
                Конфиги
                {planDirty && <span className="h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden />}
              </TabsTrigger>
              {rightsVisible && (
                <TabsTrigger value="rights" className="gap-1.5" title="Квота и права абонента">
                  <UserCog size={14} aria-hidden />
                  Права
                </TabsTrigger>
              )}
              <TabsTrigger value="account" className="gap-1.5" title="Заметка, вход в панель, Telegram">
                <Settings size={14} aria-hidden />
                Аккаунт
              </TabsTrigger>
            </TabsList>

            <div className="flex shrink-0 items-center gap-1">
              {chatEnabled && (
                <Button
                  type="button"
                  size="icon"
                  variant={activeTab === 'chat' ? 'secondary' : 'ghost'}
                  className="relative h-9 w-9"
                  aria-pressed={activeTab === 'chat'}
                  aria-label="Переписка с абонентом"
                  title="Переписка с абонентом"
                  onClick={() => handleTabChange('chat')}
                >
                  <MessageSquare size={16} />
                  {chatUnread > 0 && (
                    <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold text-destructive-foreground">
                      {chatUnread > 9 ? '9+' : chatUnread}
                    </span>
                  )}
                </Button>
              )}
              <Button
                type="button"
                size="icon"
                variant={activeTab === 'history' ? 'secondary' : 'ghost'}
                className="h-9 w-9"
                aria-pressed={activeTab === 'history'}
                aria-label="История действий"
                title="История действий"
                onClick={() => handleTabChange('history')}
              >
                <History size={16} />
              </Button>
            </div>
          </div>
        </div>

        <div className="px-4 py-4 sm:px-5">
          <TabsContent value="access" className="mt-0 space-y-4">
            <UserAccessControlSection card={card} onRefresh={onRefresh} />
          </TabsContent>
          <TabsContent value="traffic" className="mt-0 space-y-4">
            <UserTrafficSection card={card} onRefresh={onRefresh} />
          </TabsContent>
          <TabsContent value="configs" className="mt-0">
            <UserConfigsSection
              userId={user.id}
              card={card}
              onRefresh={onRefresh}
              onDirtyChange={setPlanDirty}
            />
          </TabsContent>
          {rightsVisible && (
            <TabsContent value="rights" className="mt-0">
              <UserRightsSection user={user} onRefresh={onRefresh} />
            </TabsContent>
          )}
          <TabsContent value="account" className="mt-0">
            <UserAccountSection user={user} onSave={onSave} onDelete={onDelete} />
          </TabsContent>
          <TabsContent value="history" className="mt-0">
            <Suspense fallback={<Spinner label="Загрузка истории…" className="py-8" />}>
              <UserHistorySection userId={user.id} />
            </Suspense>
          </TabsContent>
          {chatEnabled && (
            <TabsContent value="chat" className="mt-0">
              <ChatThread userId={user.id} onRead={() => setChatUnread(0)} />
            </TabsContent>
          )}
        </div>
      </Tabs>
    </div>
  )
}
