import { useEffect, useState } from 'react'
import { CalendarDays, EyeOff, Gauge, Save, SlidersHorizontal } from 'lucide-react'
import { ApiError, getUserVpnVisibilityDefault, setUserVpnVisibilityDefault } from '@/api/client'
import SelfServiceLimitsSection from '@/components/settings/SelfServiceLimitsSection'
import UserGraceSection from '@/components/settings/UserGraceSection'
import { SettingsCollapsible } from '@/components/settings/SettingsChrome'
import VpnVisibilityPolicyEditor, {
  FULL_VISIBLE_VPN_POLICY,
  copyVisibleVpnPolicy,
  isVisibleVpnPolicyEmpty,
} from '@/components/settings/VpnVisibilityPolicyEditor'
import { Button } from '@/components/ui/button'
import Spinner from '@/components/ui/Spinner'
import { useNotifications } from '@/context/NotificationContext'
import type { VisibleVpnProfilesPolicy } from '@/types'

/** Общие правила для абонентов: умолчание видимости, квоты создания и удержание конфигов. */
export default function SubscriberRulesPanel() {
  const { success, error: notifyError } = useNotifications()
  const [open, setOpen] = useState(false)
  const [policyOpen, setPolicyOpen] = useState(false)
  const [limitsOpen, setLimitsOpen] = useState(false)
  const [graceOpen, setGraceOpen] = useState(false)
  const [defaultPolicy, setDefaultPolicy] = useState<VisibleVpnProfilesPolicy>(FULL_VISIBLE_VPN_POLICY)
  const [defaultPolicyLoading, setDefaultPolicyLoading] = useState(true)
  const [savingDefaultPolicy, setSavingDefaultPolicy] = useState(false)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      setDefaultPolicyLoading(true)
      try {
        const data = await getUserVpnVisibilityDefault()
        if (!cancelled) setDefaultPolicy(copyVisibleVpnPolicy(data.policy))
      } catch (err) {
        if (!cancelled) {
          notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить умолчание видимости профилей')
        }
      } finally {
        if (!cancelled) setDefaultPolicyLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [notifyError])

  const saveDefaultVisibility = async () => {
    setSavingDefaultPolicy(true)
    try {
      const data = await setUserVpnVisibilityDefault(defaultPolicy)
      setDefaultPolicy(copyVisibleVpnPolicy(data.policy))
      success('Умолчание видимости профилей сохранено')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения умолчания')
    } finally {
      setSavingDefaultPolicy(false)
    }
  }

  return (
    <SettingsCollapsible
      open={open}
      onOpenChange={setOpen}
      title="Правила для абонентов"
      description="Видимость VPN-профилей по умолчанию, лимиты создания конфигов и удержание после истечения доступа"
      icon={<SlidersHorizontal size={16} />}
      className="rounded-2xl bg-card shadow-sm"
    >
      <SettingsCollapsible
        open={policyOpen}
        onOpenChange={setPolicyOpen}
        title="Видимость VPN-профилей по умолчанию"
        description="Что видят обычные пользователи без персонального исключения (исключение — в карточке абонента, вкладка «Аккаунт»)"
        icon={<EyeOff size={16} />}
      >
        {defaultPolicyLoading ? (
          <Spinner label="Загрузка политики..." className="py-4" />
        ) : (
          <>
            <VpnVisibilityPolicyEditor value={defaultPolicy} onChange={setDefaultPolicy} />
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                size="sm"
                onClick={() => void saveDefaultVisibility()}
                disabled={savingDefaultPolicy}
              >
                <Save size={15} />
                {savingDefaultPolicy ? 'Сохранение...' : 'Сохранить умолчание'}
              </Button>
              {isVisibleVpnPolicyEmpty(defaultPolicy) && (
                <span className="text-xs text-amber-700 dark:text-amber-300">
                  Пустой каталог — пользователи не увидят профили
                </span>
              )}
            </div>
          </>
        )}
      </SettingsCollapsible>

      <SettingsCollapsible
        open={limitsOpen}
        onOpenChange={setLimitsOpen}
        title="Лимиты создания конфигов"
        description="Квота по умолчанию и защита от массового создания"
        icon={<Gauge size={16} />}
      >
        {limitsOpen ? <SelfServiceLimitsSection /> : null}
      </SettingsCollapsible>

      <SettingsCollapsible
        open={graceOpen}
        onOpenChange={setGraceOpen}
        title="Удержание после истечения доступа"
        description="Сколько месяцев держать конфиги истёкшего абонента до ручной очистки"
        icon={<CalendarDays size={16} />}
      >
        {graceOpen ? <UserGraceSection /> : null}
      </SettingsCollapsible>
    </SettingsCollapsible>
  )
}
