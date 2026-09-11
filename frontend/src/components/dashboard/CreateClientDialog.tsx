import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Loader2, Plus } from 'lucide-react'
import {
  ApiError,
  applyClientTemplate,
  createConfig,
  setClientAccessUntil,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import type { ClientTemplate, User, VpnType } from '@/types'

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

export interface CreateClientDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  openvpnEnabled: boolean
  wireguardEnabled: boolean
  awg2CreateEnabled: boolean
  isAdmin: boolean
  currentUserId?: number
  panelUsers: User[]
  templates: ClientTemplate[]
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
  templates,
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

    const ordered = PROTOCOL_ORDER.filter((type) => selectedProtocols.includes(type))
    setSubmitting(true)
    const accessDateSnapshot = accessUntilDate
    const created: VpnType[] = []
    let lastHaWarning: string | undefined

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
        closeForm()
        await onCreated()
      }, ordered.length > 1 ? `Создание профиля (${ordered.length} конф.)...` : 'Создание клиента...')

      if (created.length === ordered.length && created.length > 0) {
        onSuccess(
          created.length === 1
            ? `Клиент «${trimmedName}» создан (${vpnLabel(created[0])})`
            : `Профиль «${trimmedName}»: ${created.map(vpnLabel).join(', ')}`,
        )
      } else if (created.length > 0) {
        onSuccess(`Профиль «${trimmedName}»: создано ${created.map(vpnLabel).join(', ')}`)
      }
      if (lastHaWarning) onWarning(lastHaWarning)
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Ошибка создания клиента')
    } finally {
      setSubmitting(false)
    }
  }

  const handleApplyTemplate = async (template: ClientTemplate) => {
    const trimmedName = clientName.trim()
    if (!trimmedName) {
      onError('Укажите имя клиента для шаблона')
      return
    }
    if (!/^[a-zA-Z0-9_-]{1,32}$/.test(trimmedName)) {
      onError('Имя: латиница, цифры, _ и -, до 32 символов')
      return
    }
    setSubmitting(true)
    const accessDateSnapshot = accessUntilDate
    try {
      await withProgress(async () => {
        const created = await applyClientTemplate(template.id, {
          client_name: trimmedName,
          owner_id: isAdmin && ownerId ? ownerId : undefined,
        })
        await applyAccessUntil(trimmedName, created.vpn_type, accessDateSnapshot)
        closeForm()
        await onCreated()
      }, `Создание: ${template.name}...`)
      onSuccess(`Клиент «${trimmedName}» создан по шаблону`)
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Ошибка применения шаблона')
    } finally {
      setSubmitting(false)
    }
  }

  const createLabel =
    selectedProtocols.length > 1
      ? `Создать · ${selectedProtocols.length}`
      : 'Создать'

  const fieldClass =
    'h-10 text-sm lg:h-11 lg:text-base xl:h-12 xl:text-base'
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
          // Phone / small tablet
          'max-h-[min(92dvh,34rem)] max-w-lg',
          'sm:max-w-xl sm:max-h-[min(90dvh,40rem)]',
          'md:max-w-2xl md:max-h-[min(88dvh,44rem)]',
          // MacBook 13–14 (~1280–1512 CSS): fill more of the laptop width
          'lg:w-[min(100vw-2rem,52rem)] lg:max-w-[52rem] lg:max-h-[min(90dvh,50rem)]',
          // MacBook 14–16 / laptop landscape
          'xl:w-[min(100vw-3rem,60rem)] xl:max-w-[60rem] xl:max-h-[min(88dvh,54rem)]',
          // Large external / ultrawide — cap growth
          '2xl:w-[min(70vw,68rem)] 2xl:max-w-[68rem] 2xl:max-h-[min(85dvh,58rem)]',
          // Short MacBook viewport (menu bar + Dock): keep usable height
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

            <div className={cn('grid gap-4', isAdmin ? 'md:grid-cols-2' : 'grid-cols-1')}>
              {isAdmin && (
                <div className="space-y-2">
                  <Label htmlFor="createAccessUntil" className="lg:text-base">
                    Доступ до
                  </Label>
                  <Input
                    id="createAccessUntil"
                    className={fieldClass}
                    type="date"
                    value={accessUntilDate}
                    onChange={(e) => setAccessUntilDate(e.target.value)}
                    disabled={submitting}
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

            {templates.length > 0 && (
              <div className="space-y-2">
                <Label className="lg:text-base">Шаблоны (one-click)</Label>
                <p className={hintClass}>
                  Шаблон создаёт одну конфигурацию по пресету — отдельно от мультивыбора выше.
                </p>
                <div className="flex flex-wrap gap-2">
                  {templates.map((tpl) => (
                    <Button
                      key={tpl.id}
                      type="button"
                      variant="secondary"
                      size="sm"
                      className="lg:h-9 lg:px-3 lg:text-sm"
                      disabled={submitting || haReplicaReadonly}
                      onClick={() => void handleApplyTemplate(tpl)}
                    >
                      {tpl.name}
                    </Button>
                  ))}
                </div>
              </div>
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
