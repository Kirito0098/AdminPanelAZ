import { useState } from 'react'
import { Save } from 'lucide-react'
import { ApiError, updateUser } from '@/api/client'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import { formatDate } from '@/lib/datetime'
import { formatBytes } from '@/lib/trafficFormat'
import type { UserUpdatePayload, UserProvisioningCard, UserProvisionSummary } from '@/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import UserAccessSection from './UserAccessSection'
import UserAccessControlSection from './UserAccessControlSection'
import UserConfigsSection from './UserConfigsSection'
import UserStatsSection from './UserStatsSection'
import UserAccountSection from './UserAccountSection'

interface UserCardProps {
  card: UserProvisioningCard
  onBack: () => void
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

export default function UserCard({ card, onBack, onSave, onDelete, onRefresh }: UserCardProps) {
  const { user } = card
  const { isEnabled } = useFeatureModules()
  const { success, error: notifyError } = useNotifications()
  const provisioningOn = isEnabled('user_provisioning')
  const [activeTab, setActiveTab] = useState<string>('access')

  const stateMeta = STATE_LABEL[user.provision_state ?? 'unmanaged']

  const handleSavePlan = async () => {
    try {
      await updateUser(user.id, { panel_login_enabled: user.panel_login_enabled })
      success('План сохранён')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения плана')
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0 pb-3 sm:space-y-0 sm:pb-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold truncate">{user.username}</span>
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
                  Истёк: удержание {card.grace_hold.elapsed_months} из {card.grace_hold.limit_months} мес.
                </Badge>
              )}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              ID {user.id} · {user.plan_config_indexes?.length ?? 0} имён конфигов ·{' '}
              {user.node_ids.length} узел{user.node_ids.length !== 1 ? 'а' : ''}
            </p>
            {user.access_until && (
              <p className="mt-0.5 text-xs text-muted-foreground">
                Срок доступа: {formatDate(user.access_until)}
              </p>
            )}
            {user.traffic_limit_bytes != null && (
              <p className="mt-0.5 text-xs text-muted-foreground">
                Трафик: {formatBytes(user.traffic_consumed_bytes ?? 0)} из{' '}
                {formatBytes(user.traffic_limit_bytes)}
                {user.traffic_counter_reset_at
                  ? ` (с ${formatDate(user.traffic_counter_reset_at)})`
                  : ''}
                {user.traffic_limit_blocked ? ' — лимит исчерпан' : ''}
              </p>
            )}
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            {provisioningOn && (
              <Button
                type="button"
                onClick={handleSavePlan}
                disabled={user.provision_state === 'unmanaged' || card.plan.blocked}
                title={
                  card.plan.blocked
                    ? 'Срок доступа истёк — сначала продлите доступ'
                    : undefined
                }
              >
                <Save size={15} />
                Применить план
              </Button>
            )}
            <Button type="button" onClick={onBack} variant="outline">
              Назад к списку
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 p-4 sm:p-5">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <TabsList className="w-auto gap-1 bg-muted/40 p-1 sm:w-auto">
              <TabsTrigger value="access">Доступ</TabsTrigger>
              <TabsTrigger value="configs">Конфиги</TabsTrigger>
              <TabsTrigger value="stats">Статистика</TabsTrigger>
              <TabsTrigger value="account">Учётная запись</TabsTrigger>
            </TabsList>

            <TabsContent value="access" className="mt-3 space-y-4">
              <UserAccessControlSection card={card} onRefresh={onRefresh} />
              <UserAccessSection card={card} onSave={onSave} />
            </TabsContent>
            <TabsContent value="configs" className="mt-3">
              <UserConfigsSection userId={user.id} card={card} />
            </TabsContent>
            <TabsContent value="stats" className="mt-3">
              <UserStatsSection userId={user.id} />
            </TabsContent>
            <TabsContent value="account" className="mt-3">
              <UserAccountSection user={user} onSave={onSave} onDelete={onDelete} />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  )
}
