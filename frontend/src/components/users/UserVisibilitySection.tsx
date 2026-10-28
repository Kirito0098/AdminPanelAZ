import { useEffect, useState } from 'react'
import { EyeOff, Save } from 'lucide-react'
import { ApiError, getUserVpnVisibilityDefault, updateUser } from '@/api/client'
import VpnVisibilityPolicyEditor, {
  FULL_VISIBLE_VPN_POLICY,
  copyVisibleVpnPolicy,
} from '@/components/settings/VpnVisibilityPolicyEditor'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import Spinner from '@/components/ui/Spinner'
import { useNotifications } from '@/context/NotificationContext'
import { cn } from '@/lib/utils'
import type { UserProvisionSummary, VisibleVpnProfilesPolicy } from '@/types'
import UserSection from './UserSection'

interface UserVisibilitySectionProps {
  user: UserProvisionSummary
  onRefresh: () => void
}

/** Персональное исключение видимости VPN-профилей: заменяет глобальное умолчание целиком. */
export default function UserVisibilitySection({ user, onRefresh }: UserVisibilitySectionProps) {
  const { success, error: notifyError } = useNotifications()
  const [defaultPolicy, setDefaultPolicy] = useState<VisibleVpnProfilesPolicy>(FULL_VISIBLE_VPN_POLICY)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [useCustom, setUseCustom] = useState(user.visible_vpn_profiles != null)
  const [draft, setDraft] = useState<VisibleVpnProfilesPolicy>(() =>
    copyVisibleVpnPolicy(user.visible_vpn_profiles),
  )

  const hadOverride = user.visible_vpn_profiles != null

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const data = await getUserVpnVisibilityDefault()
        if (cancelled) return
        const loaded = copyVisibleVpnPolicy(data.policy)
        setDefaultPolicy(loaded)
        if (!hadOverride) setDraft(loaded)
      } catch (err) {
        if (!cancelled) {
          notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить умолчание видимости профилей')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [hadOverride, notifyError])

  const handleSave = async () => {
    setSaving(true)
    try {
      await updateUser(user.id, { visible_vpn_profiles: useCustom ? draft : null })
      success(useCustom ? 'Своя политика видимости сохранена' : 'Видимость: как умолчание')
      onRefresh()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения видимости')
    } finally {
      setSaving(false)
    }
  }

  const modeButton = (custom: boolean, label: string) => (
    <button
      type="button"
      onClick={() => {
        setUseCustom(custom)
        if (custom && !useCustom) setDraft(copyVisibleVpnPolicy(defaultPolicy))
      }}
      disabled={saving}
      className={cn(
        'rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors',
        useCustom === custom ? 'border-primary bg-primary/10 text-primary' : 'hover:bg-muted/50',
      )}
    >
      {label}
    </button>
  )

  return (
    <UserSection
      icon={EyeOff}
      title="Видимость VPN-профилей"
      description="Исключение полностью заменяет глобальное умолчание из Настроек → Пользователи."
      actions={
        <Badge variant={hadOverride ? 'default' : 'secondary'} className="text-[10px]">
          {hadOverride ? 'Своя политика' : 'Как умолчание'}
        </Badge>
      }
    >
      {loading ? (
        <Spinner label="Загрузка политики…" className="py-4" />
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {modeButton(false, 'Как умолчание')}
            {modeButton(true, 'Своя политика')}
          </div>
          {useCustom && <VpnVisibilityPolicyEditor value={draft} onChange={setDraft} disabled={saving} />}
          <Button type="button" onClick={() => void handleSave()} disabled={saving}>
            <Save size={15} />
            {saving ? 'Сохранение…' : 'Сохранить'}
          </Button>
        </div>
      )}
    </UserSection>
  )
}
