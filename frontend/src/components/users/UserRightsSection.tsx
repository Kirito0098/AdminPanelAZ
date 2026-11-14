import { useState } from 'react'
import { Layers, ShieldCheck } from 'lucide-react'
import { ApiError, updateUser } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PercentBar } from '@/components/ui/percent-bar'
import { Switch } from '@/components/ui/switch'
import { useNotifications } from '@/context/NotificationContext'
import type { UserProvisionSummary } from '@/types'
import UserSection from './UserSection'
import UserVisibilitySection from './UserVisibilitySection'

interface UserRightsSectionProps {
  user: UserProvisionSummary
  onRefresh: () => void
}

/** Права абонента на свои конфиги в Telegram Mini App и веб-панели. */
function MiniAppRightsSection({
  user,
  onRefresh,
}: {
  user: UserProvisionSummary
  onRefresh: () => void
}) {
  const { success, error: notifyError } = useNotifications()
  const [canCreate, setCanCreate] = useState(user.can_create_configs !== false)
  const [canManage, setCanManage] = useState(user.can_manage_configs === true)
  const [saving, setSaving] = useState(false)

  const save = async (
    data: { can_create_configs?: boolean; can_manage_configs?: boolean },
    message: string,
    rollback: () => void,
  ) => {
    setSaving(true)
    try {
      await updateUser(user.id, data)
      success(message)
      onRefresh()
    } catch (err) {
      rollback()
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения прав')
    } finally {
      setSaving(false)
    }
  }

  const toggleCreate = (next: boolean) => {
    setCanCreate(next)
    void save(
      { can_create_configs: next },
      next ? 'Создание конфигураций разрешено' : 'Создание конфигураций запрещено',
      () => setCanCreate(!next),
    )
  }

  const toggleManage = (next: boolean) => {
    setCanManage(next)
    void save(
      { can_manage_configs: next },
      next ? 'Управление конфигурациями разрешено' : 'Управление конфигурациями запрещено',
      () => setCanManage(!next),
    )
  }

  return (
    <UserSection
      icon={ShieldCheck}
      title="Права в Mini App"
      description="Что абонент может делать со своими конфигами в Telegram Mini App и веб-панели."
    >
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-3 rounded-lg border bg-muted/20 px-3 py-2.5">
          <div className="space-y-0.5">
            <Label htmlFor="accountCanCreate">Может создавать конфигурации</Label>
            <p className="text-xs text-muted-foreground">
              Выкл. — только просмотр и скачивание своих конфигов.
            </p>
          </div>
          <Switch
            id="accountCanCreate"
            checked={canCreate}
            disabled={saving}
            onCheckedChange={toggleCreate}
          />
        </div>
        <div className="flex items-center justify-between gap-3 rounded-lg border bg-muted/20 px-3 py-2.5">
          <div className="space-y-0.5">
            <Label htmlFor="accountCanManage">Может управлять конфигурациями</Label>
            <p className="text-xs text-muted-foreground">
              Выкл. — только получение и скачивание: продление сертификата и удаление недоступны.
            </p>
          </div>
          <Switch
            id="accountCanManage"
            checked={canManage}
            disabled={saving}
            onCheckedChange={toggleManage}
          />
        </div>
      </div>
    </UserSection>
  )
}

/** Права и лимиты абонента: квота имён, права в Mini App, видимость VPN-профилей. */
export default function UserRightsSection({ user, onRefresh }: UserRightsSectionProps) {
  const { success, error: notifyError } = useNotifications()
  const [quotaInput, setQuotaInput] = useState(
    user.config_quota != null ? String(user.config_quota) : '',
  )
  const [quotaSaving, setQuotaSaving] = useState(false)

  const used = user.plan_config_indexes?.length ?? 0
  const limit = user.config_quota ?? null
  const quotaPercent = limit && limit > 0 ? Math.min((used / limit) * 100, 100) : 0

  const handleSaveQuota = async () => {
    const trimmed = quotaInput.trim()
    let value: number | null = null
    if (trimmed) {
      const parsed = Number.parseInt(trimmed, 10)
      if (!Number.isFinite(parsed) || parsed < 0) {
        notifyError('Квота — целое число ≥ 0 или пусто')
        return
      }
      value = parsed
    }
    setQuotaSaving(true)
    try {
      await updateUser(user.id, { config_quota: value })
      success('Квота сохранена')
      onRefresh()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось сохранить квоту')
    } finally {
      setQuotaSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <UserSection
        icon={Layers}
        title="Квота конфигов"
        description="Лимит имён конфигов на всех серверах."
        actions={
          <Badge variant="secondary">
            {used} / {limit ?? '∞'}
          </Badge>
        }
      >
        <div className="space-y-2">
          {limit != null && limit > 0 && (
            <PercentBar
              value={used}
              max={limit}
              className="h-2"
              barClassName={
                quotaPercent >= 100
                  ? 'fill-destructive'
                  : quotaPercent >= 80
                    ? 'fill-amber-500'
                    : 'fill-primary'
              }
              label="Использование квоты конфигов"
            />
          )}
          <p className="text-xs text-muted-foreground">
            {limit == null
              ? 'Без личной квоты — действует общий лимит панели.'
              : 'Достижение квоты блокирует добавление имён.'}
          </p>
          <div className="flex items-end gap-2">
            <div className="space-y-1">
              <Label htmlFor="quotaInput">Квота конфигов</Label>
              <Input
                id="quotaInput"
                inputMode="numeric"
                value={quotaInput}
                onChange={(e) => setQuotaInput(e.target.value)}
                placeholder="без квоты"
                className="h-9 w-32"
              />
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={() => void handleSaveQuota()}
              disabled={quotaSaving}
            >
              Сохранить
            </Button>
          </div>
        </div>
      </UserSection>

      <MiniAppRightsSection user={user} onRefresh={onRefresh} />
      <UserVisibilitySection user={user} onRefresh={onRefresh} />
    </div>
  )
}
