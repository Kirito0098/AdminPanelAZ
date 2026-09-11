import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Loader2, Plus } from 'lucide-react'
import { ApiError } from '@/api/client'
import ConfigOwnerSelect from '@/components/dashboard/ConfigOwnerSelect'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  createTgPanelConfig,
  getTgPanelUsers,
  setTgClientAccessUntil,
  tgAwg2SetTrafficLimit,
  tgOpenvpnSetTrafficLimit,
  tgWgSetTrafficLimit,
} from '@/tg-mini/api'
import { AWG2_TTL_OPTIONS } from '@/components/awg2/utils'
import { cn } from '@/lib/utils'
import type { SelfServiceQuota, User, VpnType } from '@/types'

const PROTOCOL_ORDER: VpnType[] = ['openvpn', 'wireguard', 'amneziawg2']

function vpnLabel(type: VpnType): string {
  if (type === 'openvpn') return 'OpenVPN'
  if (type === 'wireguard') return 'WG/AWG 1.5'
  return 'AWG 2.0'
}

async function setTrafficLimitForProtocol(
  protocol: VpnType,
  clientName: string,
  value: number,
  unit: string,
  periodDays: number | null,
) {
  if (protocol === 'openvpn') {
    await tgOpenvpnSetTrafficLimit(clientName, value, unit, periodDays)
    return
  }
  if (protocol === 'amneziawg2') {
    await tgAwg2SetTrafficLimit(clientName, value, unit, periodDays)
    return
  }
  await tgWgSetTrafficLimit(clientName, value, unit, periodDays)
}

interface CreateConfigDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  isAdmin: boolean
  currentUserId?: number
  openvpnEnabled: boolean
  wireguardEnabled: boolean
  awg2Enabled: boolean
  quota: SelfServiceQuota | null
  onCreated: () => void
}

export default function CreateConfigDialog({
  open,
  onOpenChange,
  isAdmin,
  currentUserId,
  openvpnEnabled,
  wireguardEnabled,
  awg2Enabled,
  quota,
  onCreated,
}: CreateConfigDialogProps) {
  const availableProtocols = useMemo(
    () =>
      PROTOCOL_ORDER.filter((type) => {
        if (type === 'openvpn') return openvpnEnabled
        if (type === 'wireguard') return wireguardEnabled
        return awg2Enabled
      }),
    [openvpnEnabled, wireguardEnabled, awg2Enabled],
  )

  const [clientName, setClientName] = useState('')
  const [description, setDescription] = useState('')
  const [selectedProtocols, setSelectedProtocols] = useState<VpnType[]>([])
  const [certDays, setCertDays] = useState('3650')
  const [ttl, setTtl] = useState<string>('none')
  const [accessUntilDate, setAccessUntilDate] = useState('')
  const [ownerId, setOwnerId] = useState<number | null>(currentUserId ?? null)
  const [users, setUsers] = useState<User[]>([])
  const [trafficLimitEnabled, setTrafficLimitEnabled] = useState(false)
  const [limitValue, setLimitValue] = useState('50')
  const [limitUnit, setLimitUnit] = useState('GB')
  const [limitPeriodDays, setLimitPeriodDays] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setSelectedProtocols(availableProtocols)
    setTtl('none')
    setAccessUntilDate('')
    setOwnerId(currentUserId ?? null)
    setTrafficLimitEnabled(false)
    setLimitValue('50')
    setLimitUnit('GB')
    setLimitPeriodDays('')
    setError(null)
  }, [open, availableProtocols, currentUserId])

  useEffect(() => {
    if (!open || !isAdmin) return
    void getTgPanelUsers()
      .then(setUsers)
      .catch(() => setUsers([]))
  }, [open, isAdmin])

  const resetForm = () => {
    setClientName('')
    setDescription('')
    setSelectedProtocols(availableProtocols)
    setCertDays('3650')
    setTtl('none')
    setAccessUntilDate('')
    setOwnerId(currentUserId ?? null)
    setTrafficLimitEnabled(false)
    setLimitValue('50')
    setLimitUnit('GB')
    setLimitPeriodDays('')
    setError(null)
  }

  const handleClose = () => {
    onOpenChange(false)
    resetForm()
  }

  const validateClientName = (trimmedName: string): string | null => {
    if (!trimmedName) return 'Укажите имя клиента'
    if (!/^[a-zA-Z0-9_-]{1,32}$/.test(trimmedName)) {
      return 'Имя: латиница, цифры, _ и -, до 32 символов'
    }
    return null
  }

  const dateInputToIso = (value: string) => {
    if (!value) return null
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
    if (!match) return null
    const next = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 23, 59, 59, 999)
    return next.toISOString()
  }

  const applyAccessUntilAfterCreate = async (
    name: string,
    protocol: VpnType,
    dateValue: string,
  ): Promise<string | null> => {
    if (!isAdmin || !dateValue) return null
    if (protocol !== 'openvpn' && protocol !== 'wireguard' && protocol !== 'amneziawg2') {
      return 'дата доступа не применена для этого протокола'
    }
    const iso = dateInputToIso(dateValue)
    if (!iso) return 'некорректная дата доступа'
    try {
      await setTgClientAccessUntil(protocol, name, iso)
      return null
    } catch (err) {
      return err instanceof ApiError ? err.message : 'срок доступа не сохранён'
    }
  }

  const finishCreate = (extraErr: string | null) => {
    window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
    onCreated()
    handleClose()
    if (extraErr) {
      window.Telegram?.WebApp.showAlert?.(extraErr)
    }
  }

  const toggleProtocol = (type: VpnType) => {
    setSelectedProtocols((prev) =>
      prev.includes(type) ? prev.filter((item) => item !== type) : [...prev, type],
    )
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const trimmedName = clientName.trim()
    const nameError = validateClientName(trimmedName)
    if (nameError) {
      setError(nameError)
      return
    }
    if (selectedProtocols.length === 0) {
      setError('Выберите хотя бы одну конфигурацию')
      return
    }
    const parsedCertDays = Number(certDays)
    if (
      selectedProtocols.includes('openvpn') &&
      (!Number.isFinite(parsedCertDays) || parsedCertDays < 1 || parsedCertDays > 3650)
    ) {
      setError('Срок сертификата: от 1 до 3650 дней')
      return
    }
    let parsedLimit: number | null = null
    let period: number | null = null
    if (isAdmin && trafficLimitEnabled) {
      parsedLimit = Number.parseFloat(limitValue)
      if (!Number.isFinite(parsedLimit) || parsedLimit <= 0) {
        setError('Укажите корректный лимит трафика')
        return
      }
      period = limitPeriodDays ? Number.parseInt(limitPeriodDays, 10) : null
      if (period != null && ![1, 7, 30].includes(period)) {
        setError('Период лимита: 1, 7 или 30 дней')
        return
      }
    }

    setSubmitting(true)
    setError(null)
    const accessDateSnapshot = accessUntilDate
    const ordered = PROTOCOL_ORDER.filter((type) => selectedProtocols.includes(type))
    const created: VpnType[] = []
    let extraErr: string | null = null
    try {
      for (const vpnType of ordered) {
        try {
          await createTgPanelConfig({
            client_name: trimmedName,
            vpn_type: vpnType,
            cert_expire_days: vpnType === 'openvpn' ? parsedCertDays : undefined,
            description: description.trim() || undefined,
            owner_id: isAdmin && ownerId ? ownerId : undefined,
            ttl: vpnType === 'amneziawg2' && ttl !== 'none' ? ttl : undefined,
          })
          created.push(vpnType)
          const nextAccessErr = await applyAccessUntilAfterCreate(
            trimmedName,
            vpnType,
            accessDateSnapshot,
          )
          if (nextAccessErr) {
            extraErr = `Клиент создан, но срок доступа не сохранён: ${nextAccessErr}`
          }
        } catch (err) {
          if (created.length === 0) throw err
          setError(
            `Создано: ${created.map(vpnLabel).join(', ')}. Не удалось: ${vpnLabel(vpnType)} — ${
              err instanceof ApiError ? err.message : 'ошибка'
            }`,
          )
          onCreated()
          return
        }
      }
      if (parsedLimit != null && created.length > 0) {
        const failed: string[] = []
        for (const protocol of created) {
          try {
            await setTrafficLimitForProtocol(
              protocol,
              trimmedName,
              parsedLimit,
              limitUnit,
              period,
            )
          } catch (err) {
            failed.push(
              `${vpnLabel(protocol)}: ${err instanceof ApiError ? err.message : 'ошибка'}`,
            )
          }
        }
        if (failed.length > 0) {
          extraErr = `Профиль создан, но лимит трафика не полностью применён (${failed.join('; ')})`
        }
      }
      finishCreate(extraErr)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка создания')
    } finally {
      setSubmitting(false)
    }
  }

  const quotaReached = quota != null && !quota.unlimited && !quota.can_create
  const busy = submitting
  const createLabel =
    selectedProtocols.length > 1 ? `Создать · ${selectedProtocols.length}` : 'Создать'

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : handleClose())}>
      <DialogContent className="tg-mini-dialog-sheet tg-mini-config-sheet max-w-lg gap-0 p-0 sm:rounded-t-2xl">
        <div className="tg-mini-sheet-handle" aria-hidden />

        <form onSubmit={(e) => void handleSubmit(e)} className="tg-mini-config-sheet-form">
          <DialogHeader className="shrink-0 space-y-2 px-4 pb-3 pt-2 text-left">
            <DialogTitle className="text-base font-semibold">Новый профиль</DialogTitle>
            <DialogDescription className="text-xs leading-relaxed">
              Одно имя — несколько конфигураций на активном узле.
            </DialogDescription>
          </DialogHeader>

          <div className="tg-mini-config-sheet-body space-y-4">
            {quota && !quota.unlimited && (
              <p className="text-xs text-muted-foreground">
                Использовано {quota.used} из {quota.limit}
                {quotaReached ? ' — лимит достигнут' : ''}
              </p>
            )}

            <div className="space-y-2">
              <Label htmlFor="tg-mini-client-name">Имя профиля</Label>
              <Input
                id="tg-mini-client-name"
                value={clientName}
                onChange={(e) => setClientName(e.target.value)}
                placeholder="client_01"
                autoComplete="off"
                disabled={busy || quotaReached}
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-baseline justify-between gap-2">
                <Label>Конфигурации</Label>
                <span className="text-xs text-muted-foreground">можно несколько</span>
              </div>
              <div className="grid gap-2 grid-cols-1">
                {availableProtocols.map((type) => {
                  const checked = selectedProtocols.includes(type)
                  return (
                    <button
                      key={type}
                      type="button"
                      disabled={busy || quotaReached}
                      onClick={() => toggleProtocol(type)}
                      aria-pressed={checked}
                      className={cn(
                        'rounded-lg border px-3 py-2.5 text-left text-sm transition-colors',
                        checked ? 'border-primary bg-primary/10 text-primary' : 'hover:bg-muted/50',
                      )}
                    >
                      <span className="block font-medium">{vpnLabel(type)}</span>
                      <span className="text-xs text-muted-foreground">
                        {checked ? 'Выбрано' : 'Не выбрано'}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>

            {selectedProtocols.includes('openvpn') && (
              <div className="space-y-2">
                <Label htmlFor="tg-mini-cert-days">Срок сертификата OpenVPN (дней)</Label>
                <Input
                  id="tg-mini-cert-days"
                  type="number"
                  min={1}
                  max={3650}
                  value={certDays}
                  onChange={(e) => setCertDays(e.target.value)}
                  disabled={busy || quotaReached}
                />
              </div>
            )}

            {selectedProtocols.includes('amneziawg2') && (
              <div className="space-y-2">
                <Label htmlFor="tg-mini-awg2-ttl">TTL AWG 2.0</Label>
                <Select value={ttl} onValueChange={setTtl} disabled={busy || quotaReached}>
                  <SelectTrigger id="tg-mini-awg2-ttl">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="z-[100]">
                    {AWG2_TTL_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {isAdmin && (
              <div className="space-y-3 rounded-lg border border-border/80 p-3">
                <label className="flex cursor-pointer items-start gap-3">
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4 rounded border-input"
                    checked={trafficLimitEnabled}
                    onChange={(e) => setTrafficLimitEnabled(e.target.checked)}
                    disabled={busy || quotaReached}
                  />
                  <span>
                    <span className="block text-sm font-medium">Лимит трафика</span>
                    <span className="text-xs text-muted-foreground">
                      На все выбранные конфигурации. Без периода — на весь срок; с периодом —
                      обновление каждый день, раз в 7 дней или месяц.
                    </span>
                  </span>
                </label>
                {trafficLimitEnabled && (
                  <div className="space-y-3">
                    <div className="space-y-2">
                      <Label htmlFor="tg-mini-limit-value">Объём</Label>
                      <div className="flex gap-2">
                        <Input
                          id="tg-mini-limit-value"
                          type="number"
                          min={0.01}
                          step="any"
                          value={limitValue}
                          onChange={(e) => setLimitValue(e.target.value)}
                          disabled={busy || quotaReached}
                        />
                        <select
                          className="w-[5.5rem] shrink-0 rounded-md border border-input bg-background px-2 text-sm"
                          value={limitUnit}
                          onChange={(e) => setLimitUnit(e.target.value)}
                          disabled={busy || quotaReached}
                        >
                          <option value="MB">MB</option>
                          <option value="GB">GB</option>
                          <option value="TB">TB</option>
                        </select>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="tg-mini-limit-period">Период</Label>
                      <select
                        id="tg-mini-limit-period"
                        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                        value={limitPeriodDays}
                        onChange={(e) => setLimitPeriodDays(e.target.value)}
                        disabled={busy || quotaReached}
                      >
                        <option value="">Всё время (без сброса)</option>
                        <option value="1">1 день (календарный)</option>
                        <option value="7">7 дней (пн–вс)</option>
                        <option value="30">30 дней (месяц)</option>
                      </select>
                    </div>
                  </div>
                )}
              </div>
            )}

            {isAdmin && (
              <div className="space-y-2">
                <Label htmlFor="tg-mini-access-until">Доступ до</Label>
                <Input
                  id="tg-mini-access-until"
                  type="date"
                  value={accessUntilDate}
                  onChange={(e) => setAccessUntilDate(e.target.value)}
                  disabled={busy || quotaReached}
                />
                <p className="text-xs text-muted-foreground">
                  Необязательно. Одна дата для всех выбранных конфигураций.
                </p>
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="tg-mini-description">Описание</Label>
              <Input
                id="tg-mini-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Необязательно"
                disabled={busy || quotaReached}
              />
            </div>

            {isAdmin && (
              <ConfigOwnerSelect
                id="tg-mini-config-owner"
                users={users}
                value={ownerId}
                onChange={setOwnerId}
                disabled={busy || quotaReached}
                description="Владелец увидит все конфигурации профиля"
              />
            )}

            {error && <p className="text-destructive text-sm">{error}</p>}
          </div>

          <footer className="tg-mini-config-sheet-footer">
            <Button
              type="submit"
              className="w-full gap-2"
              size="lg"
              disabled={busy || quotaReached || selectedProtocols.length === 0}
            >
              {submitting ? (
                <Loader2 size={18} className="animate-spin" aria-hidden />
              ) : (
                <Plus size={18} aria-hidden />
              )}
              {createLabel}
            </Button>
            <Button type="button" variant="outline" className="w-full" onClick={handleClose} disabled={submitting}>
              Отмена
            </Button>
          </footer>
        </form>
      </DialogContent>
    </Dialog>
  )
}
