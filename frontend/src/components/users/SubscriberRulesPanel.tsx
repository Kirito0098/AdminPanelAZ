import { useEffect, useState } from 'react'
import { CalendarDays, ChevronDown, EyeOff, Gauge, Save, SlidersHorizontal } from 'lucide-react'
import { ApiError, getUserVpnVisibilityDefault, setUserVpnVisibilityDefault } from '@/api/client'
import SelfServiceLimitsSection from '@/components/settings/SelfServiceLimitsSection'
import UserGraceSection from '@/components/settings/UserGraceSection'
import { SettingsCollapsible } from '@/components/settings/SettingsChrome'
import VpnVisibilityPolicyEditor, {
  FULL_VISIBLE_VPN_POLICY,
  copyVisibleVpnPolicy,
  isVisibleVpnPolicyEmpty,
} from '@/components/settings/VpnVisibilityPolicyEditor'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import Spinner from '@/components/ui/Spinner'
import { useNotifications } from '@/context/NotificationContext'
import { cn } from '@/lib/utils'
import type { VisibleVpnProfilesPolicy } from '@/types'

type VisibilityState = 'all' | 'partial' | 'empty'

const VISIBILITY_BADGE: Record<
  VisibilityState,
  { label: string; variant: 'secondary' | 'outline' | 'warning' }
> = {
  all: { label: 'видимость: все', variant: 'secondary' },
  partial: { label: 'видимость: выборочно', variant: 'outline' },
  empty: { label: 'видимость: пусто', variant: 'warning' },
}

function sameValues(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((value) => right.includes(value))
}

function visibilityState(policy: VisibleVpnProfilesPolicy): VisibilityState {
  if (isVisibleVpnPolicyEmpty(policy)) return 'empty'
  const full = FULL_VISIBLE_VPN_POLICY
  const matchesFull =
    sameValues(policy.routes, full.routes) &&
    sameValues(policy.protocols, full.protocols) &&
    sameValues(policy.openvpn_groups, full.openvpn_groups) &&
    (policy.awg2_tunnel_only ?? true)
  return matchesFull ? 'all' : 'partial'
}

/** Общие правила для абонентов: умолчание видимости, квоты создания и удержание конфигов. */
export default function SubscriberRulesPanel() {
  const { success, error: notifyError } = useNotifications()
  const [open, setOpen] = useState(false)
  const [policyOpen, setPolicyOpen] = useState(false)
  const [limitsOpen, setLimitsOpen] = useState(false)
  const [graceOpen, setGraceOpen] = useState(false)
  const [defaultPolicy, setDefaultPolicy] = useState<VisibleVpnProfilesPolicy>(FULL_VISIBLE_VPN_POLICY)
  /** Сохранённое умолчание — для бейджа в шапке, пока черновик не сохранён. */
  const [savedPolicy, setSavedPolicy] = useState<VisibleVpnProfilesPolicy>(FULL_VISIBLE_VPN_POLICY)
  const [defaultPolicyLoading, setDefaultPolicyLoading] = useState(true)
  const [savingDefaultPolicy, setSavingDefaultPolicy] = useState(false)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      setDefaultPolicyLoading(true)
      try {
        const data = await getUserVpnVisibilityDefault()
        if (!cancelled) {
          const policy = copyVisibleVpnPolicy(data.policy)
          setDefaultPolicy(policy)
          setSavedPolicy(policy)
        }
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
      const policy = copyVisibleVpnPolicy(data.policy)
      setDefaultPolicy(policy)
      setSavedPolicy(policy)
      success('Умолчание видимости профилей сохранено')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения умолчания')
    } finally {
      setSavingDefaultPolicy(false)
    }
  }

  const visibilityBadge = defaultPolicyLoading
    ? null
    : VISIBILITY_BADGE[visibilityState(savedPolicy)]

  return (
    <Card className="overflow-hidden rounded-2xl border-border/80 shadow-sm">
      <div className="h-1 bg-gradient-to-r from-primary/80 via-primary/40 to-transparent" />
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-start justify-between gap-3 px-4 py-4 text-left transition-colors hover:bg-muted/20 sm:px-5"
      >
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <SlidersHorizontal size={18} />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-base font-semibold tracking-tight">Правила для абонентов</span>
              {visibilityBadge ? (
                <Badge variant={visibilityBadge.variant}>{visibilityBadge.label}</Badge>
              ) : null}
            </div>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Видимость VPN-профилей по умолчанию, лимиты создания конфигов и удержание после истечения доступа
            </p>
          </div>
        </div>
        <ChevronDown
          size={18}
          aria-hidden
          className={cn(
            'mt-0.5 shrink-0 text-muted-foreground transition-transform',
            open && 'rotate-180',
          )}
        />
      </button>

      {open ? (
        <div className="space-y-3 border-t border-border/60 px-4 py-4 sm:px-5">
          <SettingsCollapsible
            open={policyOpen}
            onOpenChange={setPolicyOpen}
            title="Видимость VPN-профилей по умолчанию"
            description="Что видят обычные пользователи без персонального исключения (исключение — в карточке абонента, вкладка «Аккаунт»)"
            icon={<EyeOff size={16} />}
            className="border-border/60"
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
            className="border-border/60"
          >
            {limitsOpen ? <SelfServiceLimitsSection /> : null}
          </SettingsCollapsible>

          <SettingsCollapsible
            open={graceOpen}
            onOpenChange={setGraceOpen}
            title="Удержание после истечения доступа"
            description="Сколько месяцев держать конфиги истёкшего абонента до ручной очистки"
            icon={<CalendarDays size={16} />}
            className="border-border/60"
          >
            {graceOpen ? <UserGraceSection /> : null}
          </SettingsCollapsible>
        </div>
      ) : null}
    </Card>
  )
}
