import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { ApiError, getNodeDefaultPolicy, updateNodeDefaultPolicy } from '@/api/client'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import Spinner from '@/components/ui/Spinner'
import { useNotifications } from '@/context/NotificationContext'
import type { NodeDefaultPolicy } from '@/types'

const ROUTE_OPTIONS = [
  { value: '', label: 'Не задано' },
  { value: 'route_selective', label: 'Выборочная (AntiZapret)' },
  { value: 'route_all', label: 'Весь трафик через VPN' },
]

const LIMIT_UNITS = ['MB', 'GB', 'TB'] as const

type NodeDefaultPolicyWizardProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  nodeId: number | null
  nodeName: string
  onSaved?: () => void
}

function formatRouteMode(mode: string | null | undefined): string {
  if (mode === 'route_all') return 'Весь трафик'
  if (mode === 'route_selective') return 'Выборочная'
  return '—'
}

export { formatRouteMode }

export default function NodeDefaultPolicyWizard({
  open,
  onOpenChange,
  nodeId,
  nodeName,
  onSaved,
}: NodeDefaultPolicyWizardProps) {
  const { success, error: notifyError } = useNotifications()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [routeMode, setRouteMode] = useState('')
  const [ovpnLimitValue, setOvpnLimitValue] = useState('')
  const [ovpnLimitUnit, setOvpnLimitUnit] = useState<string>('GB')
  const [ovpnLimitPeriod, setOvpnLimitPeriod] = useState('')
  const [ovpnClearLimit, setOvpnClearLimit] = useState(false)
  const [wgLimitValue, setWgLimitValue] = useState('')
  const [wgLimitUnit, setWgLimitUnit] = useState<string>('GB')
  const [wgLimitPeriod, setWgLimitPeriod] = useState('')
  const [wgClearLimit, setWgClearLimit] = useState(false)

  const applyPolicy = (policy: NodeDefaultPolicy) => {
    setRouteMode(policy.route_mode ?? '')
    setOvpnLimitValue(policy.openvpn.limit_value != null ? String(policy.openvpn.limit_value) : '')
    setOvpnLimitUnit(policy.openvpn.limit_unit ?? 'GB')
    setOvpnLimitPeriod(
      policy.openvpn.limit_period_days != null ? String(policy.openvpn.limit_period_days) : '',
    )
    setOvpnClearLimit(false)
    setWgLimitValue(policy.wireguard.limit_value != null ? String(policy.wireguard.limit_value) : '')
    setWgLimitUnit(policy.wireguard.limit_unit ?? 'GB')
    setWgLimitPeriod(
      policy.wireguard.limit_period_days != null ? String(policy.wireguard.limit_period_days) : '',
    )
    setWgClearLimit(false)
  }

  useEffect(() => {
    if (!open || nodeId == null) return
    setLoading(true)
    getNodeDefaultPolicy(nodeId)
      .then(applyPolicy)
      .catch((err) => {
        notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки политики узла')
      })
      .finally(() => setLoading(false))
  }, [open, nodeId, notifyError])

  const handleSave = async () => {
    if (nodeId == null) return

    const payload: import('@/types').NodeDefaultPolicyUpdate = {
      route_mode: routeMode || null,
    }

    if (ovpnClearLimit) {
      payload.openvpn_clear_limit = true
    } else if (ovpnLimitValue.trim()) {
      const value = Number.parseFloat(ovpnLimitValue)
      if (!Number.isFinite(value) || value <= 0) {
        notifyError('Укажите корректный лимит OpenVPN')
        return
      }
      payload.openvpn_limit_value = value
      payload.openvpn_limit_unit = ovpnLimitUnit
      payload.openvpn_limit_period_days = ovpnLimitPeriod ? Number.parseInt(ovpnLimitPeriod, 10) : null
    }

    if (wgClearLimit) {
      payload.wireguard_clear_limit = true
    } else if (wgLimitValue.trim()) {
      const value = Number.parseFloat(wgLimitValue)
      if (!Number.isFinite(value) || value <= 0) {
        notifyError('Укажите корректный лимит WireGuard')
        return
      }
      payload.wireguard_limit_value = value
      payload.wireguard_limit_unit = wgLimitUnit
      payload.wireguard_limit_period_days = wgLimitPeriod ? Number.parseInt(wgLimitPeriod, 10) : null
    }

    setSaving(true)
    try {
      await updateNodeDefaultPolicy(nodeId, payload)
      success(`Политика узла «${nodeName}» сохранена`)
      onSaved?.()
      onOpenChange(false)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения политики узла')
    } finally {
      setSaving(false)
    }
  }

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={`Политика узла: ${nodeName}`}
      description="Дефолтные лимиты трафика и маршрутизация для новых клиентов на этом узле (EU vs RU и т.д.)"
      confirmLabel="Сохранить"
      loading={saving}
      onConfirm={handleSave}
      className="max-w-lg"
    >
      {loading ? (
        <Spinner label="Загрузка..." className="py-6" />
      ) : (
        <div className="space-y-5 py-2">
          <div className="space-y-2">
            <Label htmlFor="node-route-mode">Маршрутизация по умолчанию</Label>
            <select
              id="node-route-mode"
              className="flex h-9 w-full rounded-md border bg-background px-3 text-sm"
              value={routeMode}
              onChange={(e) => setRouteMode(e.target.value)}
              disabled={saving}
            >
              {ROUTE_OPTIONS.map((opt) => (
                <option key={opt.value || 'none'} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <fieldset className="space-y-3 rounded-md border p-3">
            <legend className="px-1 text-sm font-medium">OpenVPN — лимит по умолчанию</legend>
            <div className="flex gap-2">
              <Input
                type="number"
                min={0.01}
                step="any"
                placeholder="Без лимита"
                value={ovpnLimitValue}
                onChange={(e) => {
                  setOvpnLimitValue(e.target.value)
                  setOvpnClearLimit(false)
                }}
                disabled={saving || ovpnClearLimit}
              />
              <select
                className="flex h-9 w-24 rounded-md border bg-background px-2 text-sm"
                value={ovpnLimitUnit}
                onChange={(e) => setOvpnLimitUnit(e.target.value)}
                disabled={saving || ovpnClearLimit}
              >
                {LIMIT_UNITS.map((unit) => (
                  <option key={unit} value={unit}>
                    {unit}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2">
              <Label htmlFor="ovpn-period" className="text-xs text-muted-foreground">
                Период
              </Label>
              <select
                id="ovpn-period"
                className="flex h-8 flex-1 rounded-md border bg-background px-2 text-sm"
                value={ovpnLimitPeriod}
                onChange={(e) => setOvpnLimitPeriod(e.target.value)}
                disabled={saving || ovpnClearLimit}
              >
                <option value="">Всё время</option>
                <option value="1">1 день</option>
                <option value="7">7 дней</option>
                <option value="30">30 дней</option>
              </select>
            </div>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={ovpnClearLimit}
                onChange={(e) => setOvpnClearLimit(e.target.checked)}
                disabled={saving}
              />
              Сбросить лимит OpenVPN
            </label>
          </fieldset>

          <fieldset className="space-y-3 rounded-md border p-3">
            <legend className="px-1 text-sm font-medium">WireGuard — лимит по умолчанию</legend>
            <div className="flex gap-2">
              <Input
                type="number"
                min={0.01}
                step="any"
                placeholder="Без лимита"
                value={wgLimitValue}
                onChange={(e) => {
                  setWgLimitValue(e.target.value)
                  setWgClearLimit(false)
                }}
                disabled={saving || wgClearLimit}
              />
              <select
                className="flex h-9 w-24 rounded-md border bg-background px-2 text-sm"
                value={wgLimitUnit}
                onChange={(e) => setWgLimitUnit(e.target.value)}
                disabled={saving || wgClearLimit}
              >
                {LIMIT_UNITS.map((unit) => (
                  <option key={unit} value={unit}>
                    {unit}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2">
              <Label htmlFor="wg-period" className="text-xs text-muted-foreground">
                Период
              </Label>
              <select
                id="wg-period"
                className="flex h-8 flex-1 rounded-md border bg-background px-2 text-sm"
                value={wgLimitPeriod}
                onChange={(e) => setWgLimitPeriod(e.target.value)}
                disabled={saving || wgClearLimit}
              >
                <option value="">Всё время</option>
                <option value="1">1 день</option>
                <option value="7">7 дней</option>
                <option value="30">30 дней</option>
              </select>
            </div>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={wgClearLimit}
                onChange={(e) => setWgClearLimit(e.target.checked)}
                disabled={saving}
              />
              Сбросить лимит WireGuard
            </label>
          </fieldset>

          {saving ? (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 size={14} className="animate-spin" />
              Сохранение...
            </p>
          ) : null}
        </div>
      )}
    </ConfirmDialog>
  )
}
