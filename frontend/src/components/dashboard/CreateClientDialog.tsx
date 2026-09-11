import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Loader2, Plus } from 'lucide-react'
import {
  ApiError,
  awg2SetTrafficLimit,
  createConfig,
  openvpnSetTrafficLimit,
  setClientAccessUntil,
  wgSetTrafficLimit,
} from '@/api/client'
import { AWG2_TTL_OPTIONS } from '@/components/awg2/utils'
import ConfigOwnerSelect from '@/components/dashboard/ConfigOwnerSelect'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import DatePickerField from '@/components/ui/DatePickerField'
import { panelToday } from '@/lib/trafficPeriod'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import type { User, VpnType } from '@/types'

const PROTOCOL_ORDER: VpnType[] = ['openvpn', 'wireguard', 'amneziawg2']

function vpnLabel(type: VpnType): string {
  if (type === 'openvpn') return 'OpenVPN'
  if (type === 'wireguard') return 'WireGuard / AmneziaWG'
  return 'AmneziaWG 2.0'
}

function vpnHint(type: VpnType): string {
  if (type === 'openvpn') return 'Сертификат + .ovpn'
  if (type === 'wireguard') return 'WG / AWG профиль'
  return 'AWG 2.0 peer'
}

function dateInputToIso(value: string): string | null {
  if (!value) return null
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return null
  const next = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 23, 59, 59, 999)
  return next.toISOString()
}

async function setTrafficLimitForProtocol(
  protocol: VpnType,
  clientName: string,
  value: number,
  unit: string,
  periodDays: number | null,
) {
  if (protocol === 'openvpn') {
    await openvpnSetTrafficLimit(clientName, value, unit, periodDays)
    return
  }
  if (protocol === 'amneziawg2') {
    await awg2SetTrafficLimit(clientName, value, unit, periodDays)
    return
  }
  await wgSetTrafficLimit(clientName, value, unit, periodDays)
}

export interface CreateClientDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  openvpnEnabled: boolean
  wireguardEnabled: boolean
  awg2CreateEnabled: boolean
  isAdmin: boolean
  currentUserId?: number
  panelUsers: User[]
  haReplicaReadonly: boolean
  onCreated: () => Promise<void> | void
  onSuccess: (message: string) => void
  onError: (message: string) => void
  onWarning: (message: string) => void
  withProgress: <T>(fn: () => Promise<T>, label: string) => Promise<T>
}

export default function CreateClientDialog({
  open,
  onOpenChange,
  openvpnEnabled,
  wireguardEnabled,
  awg2CreateEnabled,
  isAdmin,
  currentUserId,
  panelUsers,
  haReplicaReadonly,
  onCreated,
  onSuccess,
  onError,
  onWarning,
  withProgress,
}: CreateClientDialogProps) {
  const availableProtocols = useMemo(
    () =>
      PROTOCOL_ORDER.filter((type) => {
        if (type === 'openvpn') return openvpnEnabled
        if (type === 'wireguard') return wireguardEnabled
        return awg2CreateEnabled
      }),
    [openvpnEnabled, wireguardEnabled, awg2CreateEnabled],
  )

  const [clientName, setClientName] = useState('')
  const [description, setDescription] = useState('')
  const [selectedProtocols, setSelectedProtocols] = useState<VpnType[]>([])
  const [certDays, setCertDays] = useState(3650)
  const [awg2Ttl, setAwg2Ttl] = useState('none')
  const [accessUntilDate, setAccessUntilDate] = useState('')
  const [ownerId, setOwnerId] = useState<number | null>(currentUserId ?? null)
  const [trafficLimitEnabled, setTrafficLimitEnabled] = useState(false)
  const [limitValue, setLimitValue] = useState('50')
  const [limitUnit, setLimitUnit] = useState('GB')
  const [limitPeriodDays, setLimitPeriodDays] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) return
    setSelectedProtocols(availableProtocols)
    setOwnerId(currentUserId ?? null)
  }, [open, availableProtocols, currentUserId])

  const resetForm = () => {
    setClientName('')
    setDescription('')
    setSelectedProtocols(availableProtocols)
    setCertDays(3650)
    setAwg2Ttl('none')
    setAccessUntilDate('')
    setOwnerId(currentUserId ?? null)
    setTrafficLimitEnabled(false)
    setLimitValue('50')
    setLimitUnit('GB')
    setLimitPeriodDays('')
  }

  const closeForm = () => {
    onOpenChange(false)
    resetForm()
  }

  const toggleProtocol = (type: VpnType) => {
    setSelectedProtocols((prev) =>
      prev.includes(type) ? prev.filter((item) => item !== type) : [...prev, type],
    )
  }

  const applyAccessUntil = async (name: string, protocol: VpnType, dateValue: string) => {
    if (!isAdmin || !dateValue) return
    const iso = dateInputToIso(dateValue)
    if (!iso) {
      onWarning(`Клиент «${name}» создан, но дата доступа некорректна — задайте её в карточке`)
      return
    }
    try {
      await setClientAccessUntil(protocol, name, iso)
    } catch (err) {
      onWarning(
        err instanceof ApiError
          ? `Клиент создан, но срок доступа не сохранён (${vpnLabel(protocol)}): ${err.message}`
          : `Клиент «${name}» создан, но срок доступа не сохранён (${vpnLabel(protocol)})`,
      )
    }
  }

  const applyTrafficLimits = async (name: string, created: VpnType[]) => {
    if (!isAdmin || !trafficLimitEnabled || created.length === 0) return null
    const value = Number.parseFloat(limitValue)
    if (!Number.isFinite(value) || value <= 0) {
      return 'лимит трафика некорректный'
    }
    const period = limitPeriodDays ? Number.parseInt(limitPeriodDays, 10) : null
    if (period != null && ![1, 7, 30].includes(period)) {
      return 'период лимита: 1, 7 или 30 дней'
    }
    const failed: string[] = []
    for (const protocol of created) {
      try {
        await setTrafficLimitForProtocol(protocol, name, value, limitUnit, period)
      } catch (err) {
        failed.push(
          `${vpnLabel(protocol)}: ${err instanceof ApiError ? err.message : 'ошибка'}`,
        )
      }
    }
    if (failed.length === created.length) {
      return `лимит трафика не применён (${failed.join('; ')})`
    }
    if (failed.length > 0) {
      return `лимит частично не применён (${failed.join('; ')})`
    }
    return null
  }

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()

    const trimmedName = clientName.trim()
    if (!trimmedName) {
      onError('Укажите имя клиента')
      return
    }
    if (!/^[a-zA-Z0-9_-]{1,32}$/.test(trimmedName)) {
      onError('Имя: латиница, цифры, _ и -, до 32 символов')
      return
    }
    if (selectedProtocols.length === 0) {
      onError('Выберите хотя бы одну конфигурацию')
      return
    }
    if (
      selectedProtocols.includes('openvpn') &&
      (!Number.isFinite(certDays) || certDays < 1 || certDays > 3650)
    ) {
      onError('Срок сертификата: от 1 до 3650 дней')
      return
    }
    if (isAdmin && trafficLimitEnabled) {
      const value = Number.parseFloat(limitValue)
      if (!Number.isFinite(value) || value <= 0) {
        onError('Укажите корректный лимит трафика')
        return
      }
      const period = limitPeriodDays ? Number.parseInt(limitPeriodDays, 10) : null
      if (period != null && ![1, 7, 30].includes(period)) {
        onError('Период лимита: 1, 7 или 30 дней')
        return
      }
    }

    const ordered = PROTOCOL_ORDER.filter((type) => selectedProtocols.includes(type))
    setSubmitting(true)
    const accessDateSnapshot = accessUntilDate
    const created: VpnType[] = []
    let lastHaWarning: string | undefined
    let trafficWarning: string | null = null

    try {
      await withProgress(async () => {
        for (const vpnType of ordered) {
          try {
            const result = await createConfig({
              client_name: trimmedName,
              vpn_type: vpnType,
              cert_expire_days: vpnType === 'openvpn' ? certDays : undefined,
              ttl: vpnType === 'amneziawg2' && awg2Ttl !== 'none' ? awg2Ttl : undefined,
              description: description || undefined,
              owner_id: isAdmin && ownerId ? ownerId : undefined,
            })
            created.push(vpnType)
            if (result.ha_replicate_warning) lastHaWarning = result.ha_replicate_warning
            await applyAccessUntil(trimmedName, vpnType, accessDateSnapshot)
          } catch (err) {
            if (created.length === 0) {
              throw err
            }
            const detail = err instanceof ApiError ? err.message : 'ошибка создания'
            onWarning(
              `Создано: ${created.map(vpnLabel).join(', ')}. Не удалось: ${vpnLabel(vpnType)} — ${detail}`,
            )
            break
          }
        }
        trafficWarning = await applyTrafficLimits(trimmedName, created)
        closeForm()
        await onCreated()
      }, ordered.length > 1 ? `Создание профиля (${ordered.length} конф.)...` : 'Создание клиента...')

      const limitNote =
        isAdmin && trafficLimitEnabled && !trafficWarning
          ? ` · лимит ${limitValue} ${limitUnit}${
              limitPeriodDays === '7'
                ? ' / 7 дн.'
                : limitPeriodDays === '30'
                  ? ' / мес'
                  : limitPeriodDays === '1'
                    ? ' / день'
                    : ''
            }`
          : ''
      if (created.length === ordered.length && created.length > 0) {
        onSuccess(
          created.length === 1
            ? `Клиент «${trimmedName}» создан (${vpnLabel(created[0])})${limitNote}`
            : `Профиль «${trimmedName}»: ${created.map(vpnLabel).join(', ')}${limitNote}`,
        )
      } else if (created.length > 0) {
        onSuccess(`Профиль «${trimmedName}»: создано ${created.map(vpnLabel).join(', ')}${limitNote}`)
      }
      if (trafficWarning) {
        onWarning(`Профиль создан, но ${trafficWarning}`)
      }
      if (lastHaWarning) onWarning(lastHaWarning)
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Ошибка создания клиента')
    } finally {
      setSubmitting(false)
    }
  }

  const createLabel =
    selectedProtocols.length > 1
      ? `Создать · ${selectedProtocols.length}`
      : 'Создать'

  const fieldClass = 'h-10 text-sm lg:h-11 lg:text-base xl:h-12 xl:text-base'
  const hintClass = 'text-xs text-muted-foreground lg:text-sm'
  const showOpenVpnOpts = selectedProtocols.includes('openvpn')
  const showAwg2Opts = selectedProtocols.includes('amneziawg2')

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !submitting) closeForm()
      }}
    >
      <DialogContent
        className={cn(
          'flex w-[calc(100vw-1.25rem)] flex-col gap-0 overflow-hidden p-0',
          'max-h-[min(92dvh,34rem)] max-w-lg',
          'sm:max-w-xl sm:max-h-[min(90dvh,40rem)]',
          'md:max-w-2xl md:max-h-[min(88dvh,44rem)]',
          'lg:w-[min(100vw-2rem,52rem)] lg:max-w-[52rem] lg:max-h-[min(90dvh,50rem)]',
          'xl:w-[min(100vw-3rem,60rem)] xl:max-w-[60rem] xl:max-h-[min(88dvh,54rem)]',
          '2xl:w-[min(70vw,68rem)] 2xl:max-w-[68rem] 2xl:max-h-[min(85dvh,58rem)]',
          'max-[920px]:lg:max-h-[min(92dvh,calc(100dvh-1.5rem))]',
          'max-[820px]:md:max-h-[min(94dvh,calc(100dvh-1rem))]',
        )}
      >
        <DialogHeader className="shrink-0 space-y-1.5 border-b px-4 py-3 text-left sm:px-6 sm:py-4 lg:px-8 lg:py-5 xl:px-10">
          <DialogTitle className="flex items-center gap-2 text-lg lg:text-xl xl:text-[1.35rem]">
            <Plus size={18} className="lg:h-5 lg:w-5" />
            Новый клиент
          </DialogTitle>
          <DialogDescription className="text-sm lg:text-base">
            Один профиль — несколько конфигураций на активном узле
          </DialogDescription>
        </DialogHeader>

        <form noValidate onSubmit={(e) => void handleCreate(e)} className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4 sm:px-6 lg:space-y-5 lg:px-8 lg:py-5 xl:px-10 xl:py-6">
            <div className="space-y-2">
              <Label htmlFor="createClientName" className="lg:text-base">
                Имя профиля
              </Label>
              <Input
                id="createClientName"
                className={fieldClass}
                value={clientName}
                onChange={(e) => setClientName(e.target.value)}
                placeholder="my-client"
                autoFocus
                disabled={submitting}
              />
              <p className={hintClass}>
                Латиница, цифры, <span className="font-medium">_</span> и{' '}
                <span className="font-medium">-</span>, до 32 символов. Одно имя для всех выбранных
                конфигураций.
              </p>
            </div>

            <div className="space-y-2">
              <div className="flex items-baseline justify-between gap-2">
                <Label className="lg:text-base">Конфигурации</Label>
                <span className={hintClass}>можно несколько</span>
              </div>
              <div className="grid gap-2 sm:grid-cols-3 sm:gap-3 xl:gap-4">
                {availableProtocols.map((type) => {
                  const checked = selectedProtocols.includes(type)
                  return (
                    <button
                      key={type}
                      type="button"
                      disabled={submitting}
                      onClick={() => toggleProtocol(type)}
                      aria-pressed={checked}
                      className={cn(
                        'rounded-lg border px-3 py-2.5 text-left text-sm transition-colors',
                        'lg:px-4 lg:py-3.5 lg:text-base xl:min-h-[4.75rem] xl:py-4',
                        checked ? 'border-primary bg-primary/10 text-primary' : 'hover:bg-muted/50',
                      )}
                    >
                      <span className="block font-medium leading-tight">{vpnLabel(type)}</span>
                      <span className="mt-0.5 block text-xs text-muted-foreground lg:mt-1 lg:text-sm">
                        {checked ? vpnHint(type) : 'Не выбрано'}
                      </span>
                    </button>
                  )
                })}
              </div>
              {availableProtocols.length === 0 && (
                <p className="text-xs text-destructive lg:text-sm">Нет доступных протоколов на этом узле.</p>
              )}
            </div>

            {(showOpenVpnOpts || showAwg2Opts) && (
              <div
                className={cn(
                  'grid gap-4',
                  showOpenVpnOpts && showAwg2Opts ? 'md:grid-cols-2' : 'grid-cols-1',
                )}
              >
                {showOpenVpnOpts && (
                  <div className="space-y-2">
                    <Label htmlFor="createCertDays" className="lg:text-base">
                      Срок сертификата OpenVPN (дней)
                    </Label>
                    <Input
                      id="createCertDays"
                      className={fieldClass}
                      type="number"
                      min={1}
                      max={3650}
                      value={certDays}
                      onChange={(e) => setCertDays(Number(e.target.value))}
                      disabled={submitting}
                    />
                  </div>
                )}
                {showAwg2Opts && (
                  <div className="space-y-2">
                    <Label htmlFor="createAwg2Ttl" className="lg:text-base">
                      TTL AmneziaWG 2.0
                    </Label>
                    <Select value={awg2Ttl} onValueChange={setAwg2Ttl} disabled={submitting}>
                      <SelectTrigger id="createAwg2Ttl" className={fieldClass}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {AWG2_TTL_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>
            )}

            {isAdmin && (
              <div className="space-y-3 rounded-lg border border-border/80 p-3 sm:p-4">
                <label className="flex cursor-pointer items-start gap-3">
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4 rounded border-input"
                    checked={trafficLimitEnabled}
                    onChange={(e) => setTrafficLimitEnabled(e.target.checked)}
                    disabled={submitting}
                  />
                  <span>
                    <span className="block text-sm font-medium lg:text-base">Лимит трафика</span>
                    <span className={hintClass}>
                      Один лимит на все выбранные конфигурации. Без периода — на весь срок жизни
                      конфига; с периодом — счётчик обновляется каждый день, раз в 7 дней или раз в
                      месяц.
                    </span>
                  </span>
                </label>
                {trafficLimitEnabled && (
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="createTrafficLimit" className="lg:text-base">
                        Объём
                      </Label>
                      <div className="flex gap-2">
                        <Input
                          id="createTrafficLimit"
                          className={fieldClass}
                          type="number"
                          min={0.01}
                          step="any"
                          value={limitValue}
                          onChange={(e) => setLimitValue(e.target.value)}
                          disabled={submitting}
                        />
                        <select
                          className={cn(
                            'rounded-md border border-input bg-background px-2 text-sm',
                            fieldClass,
                            'w-[5.5rem] shrink-0',
                          )}
                          value={limitUnit}
                          onChange={(e) => setLimitUnit(e.target.value)}
                          disabled={submitting}
                        >
                          <option value="MB">MB</option>
                          <option value="GB">GB</option>
                          <option value="TB">TB</option>
                        </select>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="createTrafficPeriod" className="lg:text-base">
                        Период
                      </Label>
                      <select
                        id="createTrafficPeriod"
                        className={cn(
                          'w-full rounded-md border border-input bg-background px-3 text-sm',
                          fieldClass,
                        )}
                        value={limitPeriodDays}
                        onChange={(e) => setLimitPeriodDays(e.target.value)}
                        disabled={submitting}
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

            <div className={cn('grid gap-4', isAdmin ? 'md:grid-cols-2' : 'grid-cols-1')}>
              {isAdmin && (
                <div className="space-y-2">
                  <Label htmlFor="createAccessUntil" className="lg:text-base">
                    Доступ до
                  </Label>
                  <DatePickerField
                    id="createAccessUntil"
                    value={accessUntilDate}
                    onChange={setAccessUntilDate}
                    disabled={submitting}
                    fromDate={panelToday()}
                  />
                  <p className={hintClass}>Необязательно. Одна дата для всех выбранных конфигураций.</p>
                </div>
              )}
              <div className="space-y-2">
                <Label htmlFor="createDescription" className="lg:text-base">
                  Описание
                </Label>
                <Input
                  id="createDescription"
                  className={fieldClass}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Необязательно"
                  disabled={submitting}
                />
              </div>
            </div>

            {isAdmin && (
              <ConfigOwnerSelect
                id="createConfigOwner"
                users={panelUsers}
                value={ownerId}
                onChange={setOwnerId}
                disabled={submitting}
                description="Владелец увидит все созданные конфигурации этого профиля."
              />
            )}
          </div>

          <DialogFooter className="shrink-0 gap-2 border-t px-4 py-3 sm:gap-0 sm:px-6 sm:py-4 lg:px-8 lg:py-5 xl:px-10">
            <Button
              type="button"
              variant="outline"
              className="lg:h-11 lg:px-5 lg:text-base xl:h-12"
              onClick={closeForm}
              disabled={submitting}
            >
              Отмена
            </Button>
            <Button
              type="submit"
              className="lg:h-11 lg:px-5 lg:text-base xl:h-12"
              disabled={submitting || haReplicaReadonly || selectedProtocols.length === 0}
            >
              {submitting ? (
                <>
                  <Loader2 size={16} className="animate-spin lg:h-[18px] lg:w-[18px]" />
                  Создание...
                </>
              ) : (
                <>
                  <Plus size={16} className="lg:h-[18px] lg:w-[18px]" />
                  {createLabel}
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
