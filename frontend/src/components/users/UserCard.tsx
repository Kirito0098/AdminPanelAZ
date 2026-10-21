import { useState } from 'react'
import { Activity, BarChart3, CalendarClock, KeyRound, Save, UserCog } from 'lucide-react'
import { ApiError, updateUser } from '@/api/client'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import { formatDate } from '@/lib/datetime'
import { formatBytes } from '@/lib/trafficFormat'
import type { UserUpdatePayload, UserProvisioningCard, UserProvisionSummary } from '@/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { PercentBar } from '@/components/ui/percent-bar'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import UserMetric from './UserMetric'
import UserAccessSection from './UserAccessSection'
import UserAccessControlSection from './UserAccessControlSection'
import UserConfigsSection from './UserConfigsSection'
import UserStatsSection from './UserStatsSection'
import UserAccountSection from './UserAccountSection'

interface UserCardProps {
  card: UserProvisioningCard
  onSave: (id: number, data: Partial<UserUpdatePayload>) => void
  onDelete: (user: UserProvisionSummary) => void
  onRefresh: () => void
}

type BadgeVariant = 'default' | 'secondary' | 'destructive' | 'outline' | 'success' | 'warning'

const STATE_LABEL: Record<string, { label: string; variant: BadgeVariant }> = {
  unmanaged: { label: 'Без набора', variant: 'secondary' },
  pending: { label: 'Применяется', variant: 'default' },
  partial: { label: 'Требует внимания', variant: 'warning' },
  ok: { label: 'OK', variant: 'success' },
}

export default function UserCard({ card, onSave, onDelete, onRefresh }: UserCardProps) {
  const { user } = card
  const { isEnabled } = useFeatureModules()
  const { success, error: notifyError } = useNotifications()
  const provisioningOn = isEnabled('user_provisioning')
  const [activeTab, setActiveTab] = useState<string>('access')

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
    : accessDaysLeft == null
      ? '—'
      : accessDaysLeft < 0
        ? `истёк ${Math.abs(accessDaysLeft)} дн.`
        : accessDaysLeft === 0
          ? 'истекает сегодня'
          : `осталось ${accessDaysLeft} дн.`
  const accessTone = accessExpired ? 'danger' : accessExpiring ? 'warning' : 'default'
  const trafficTone = user.traffic_limit_blocked ? 'danger' : trafficPercent >= 80 ? 'warning' : 'default'

  const handleSavePlan = async () => {
    try {
      await updateUser(user.id, { panel_login_enabled: user.panel_login_enabled })
      success('План сохранён')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения плана')
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <Card className="border-0 bg-transparent shadow-none">
        <CardHeader className="gap-0 space-y-0 rounded-xl border bg-muted/20 p-4 sm:p-5">
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-start gap-3">
              <span
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold uppercase text-primary"
                aria-hidden
              >
                {initials}
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="truncate text-base font-semibold leading-tight">{user.username}</span>
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
                <p className="mt-1 text-xs text-muted-foreground">
                  ID {user.id} · {configCount} имён конфигов · {user.node_ids.length} узел
                  {user.node_ids.length !== 1 ? 'а' : ''}
                </p>
              </div>
            </div>
            {provisioningOn && (
              <Button
                type="button"
                onClick={handleSavePlan}
                disabled={user.provision_state === 'unmanaged' || card.plan.blocked}
                className="shrink-0"
                title={card.plan.blocked ? 'Срок доступа истёк — сначала продлите доступ' : undefined}
              >
                <Save size={15} />
                Применить план
              </Button>
            )}
          </div>

          <div className="mt-4 grid gap-2 sm:grid-cols-3">
            <UserMetric
              icon={CalendarClock}
              label="Срок доступа"
              tone={accessTone}
              value={accessLabel}
              hint={accessUntil ? `до ${formatDate(accessUntil)}` : 'срок не задан'}
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
              hint={quota != null ? 'квота имён' : 'квота не задана'}
            />
          </div>
        </CardHeader>
        <CardContent className="p-0 sm:p-0">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="mt-3 w-full">
            <TabsList className="w-full justify-start gap-1 overflow-x-auto bg-muted/50 p-1 sm:w-auto">
              <TabsTrigger value="access" className="gap-1.5">
                <CalendarClock size={14} aria-hidden />
                Доступ
              </TabsTrigger>
              <TabsTrigger value="configs" className="gap-1.5">
                <KeyRound size={14} aria-hidden />
                Конфиги
              </TabsTrigger>
              <TabsTrigger value="stats" className="gap-1.5">
                <BarChart3 size={14} aria-hidden />
                Статистика
              </TabsTrigger>
              <TabsTrigger value="account" className="gap-1.5">
                <UserCog size={14} aria-hidden />
                Учётная запись
              </TabsTrigger>
            </TabsList>

            <TabsContent value="access" className="mt-4 space-y-4">
              <UserAccessControlSection card={card} onRefresh={onRefresh} />
              <UserAccessSection card={card} onSave={onSave} onRefresh={onRefresh} />
            </TabsContent>
            <TabsContent value="configs" className="mt-4">
              <UserConfigsSection userId={user.id} card={card} />
            </TabsContent>
            <TabsContent value="stats" className="mt-4">
              <UserStatsSection userId={user.id} />
            </TabsContent>
            <TabsContent value="account" className="mt-4">
              <UserAccountSection user={user} onSave={onSave} onDelete={onDelete} />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  )
}
