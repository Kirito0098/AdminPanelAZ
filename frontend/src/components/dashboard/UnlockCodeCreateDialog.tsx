import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Copy, KeyRound, Loader2, X } from 'lucide-react'
import { getConfigs } from '@/api/configs'
import { createUnlockCode, type UnlockCodeProtocol } from '@/api/unlockCodes'
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
import { Badge } from '@/components/ui/badge'
import { useNotifications } from '@/context/NotificationContext'
import { formatDate } from '@/lib/datetime'
import { cn } from '@/lib/utils'
import type { UnlockCodeRecord, VpnType } from '@/types'

const ALL_PROTOCOLS: UnlockCodeProtocol[] = ['openvpn', 'wireguard', 'amneziawg2']

type ClientOption = {
  name: string
  protocols: UnlockCodeProtocol[]
}

function protocolLabel(protocol: UnlockCodeProtocol) {
  if (protocol === 'openvpn') return 'OpenVPN'
  // One WG access policy covers both portal tabs WireGuard and AmneziaWG (vpn_type=wireguard).
  if (protocol === 'wireguard') return 'WireGuard / AmneziaWG'
  return 'AmneziaWG 2.0'
}

function shortProtocolLabel(protocol: UnlockCodeProtocol) {
  if (protocol === 'openvpn') return 'OVPN'
  if (protocol === 'wireguard') return 'WG'
  return 'AWG2'
}

function toUnlockProtocol(vpnType: VpnType | string): UnlockCodeProtocol | null {
  if (vpnType === 'openvpn' || vpnType === 'wireguard' || vpnType === 'amneziawg2') return vpnType
  return null
}

function toEndOfDayIso(value: string) {
  if (!value) return null
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return null
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 23, 59, 59, 999)
  return date.toISOString()
}

function normalizeClientName(value: string) {
  return value.trim().toLowerCase()
}

function clientMatchesProtocols(client: ClientOption, protocols: UnlockCodeProtocol[]) {
  if (protocols.length === 0) return false
  return client.protocols.some((protocol) => protocols.includes(protocol))
}

interface UnlockCodeCreateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialProtocols?: UnlockCodeProtocol[]
  availableProtocols?: UnlockCodeProtocol[]
  initialClientNames?: string[]
  onCreated?: (code: UnlockCodeRecord) => Promise<void> | void
}

export default function UnlockCodeCreateDialog({
  open,
  onOpenChange,
  initialProtocols = ['openvpn'],
  availableProtocols = ALL_PROTOCOLS,
  initialClientNames = [],
  onCreated,
}: UnlockCodeCreateDialogProps) {
  const { success, error: notifyError } = useNotifications()
  const availableProtocolsKey = availableProtocols.join(',')
  const initialProtocolsKey = initialProtocols.join(',')
  const initialClientsKey = initialClientNames.map(normalizeClientName).filter(Boolean).join(',')
  const protocolOptions = useMemo(
    () => ALL_PROTOCOLS.filter((protocol) => availableProtocols.includes(protocol)),
    [availableProtocolsKey],
  )
  const [grantDays, setGrantDays] = useState('30')
  const [mode, setMode] = useState<'single' | 'multi'>('single')
  const [maxRedemptions, setMaxRedemptions] = useState('10')
  const [codeExpiresAt, setCodeExpiresAt] = useState('')
  const [selectedProtocols, setSelectedProtocols] = useState<UnlockCodeProtocol[]>([])
  const [clientOptions, setClientOptions] = useState<ClientOption[]>([])
  const [clientSearch, setClientSearch] = useState('')
  const [selectedClients, setSelectedClients] = useState<string[]>([])
  const [clientsLoading, setClientsLoading] = useState(false)
  const [createdCode, setCreatedCode] = useState<UnlockCodeRecord | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    const nextProtocols = initialProtocols.filter((protocol) => protocolOptions.includes(protocol))
    const nextClients = Array.from(
      new Set(initialClientNames.map(normalizeClientName).filter(Boolean)),
    )
    setGrantDays('30')
    setMode('single')
    setMaxRedemptions('10')
    setCodeExpiresAt('')
    // For a specific client (or Subscription create), default to every available protocol so
    // portal "Истекает" (min across protocols) actually moves after redeem.
    const defaultProtocols =
      nextClients.length > 0 || nextProtocols.length === 0
        ? protocolOptions
        : nextProtocols.length > 0
          ? nextProtocols
          : protocolOptions.slice(0, 1)
    setSelectedProtocols(defaultProtocols.length > 0 ? defaultProtocols : protocolOptions.slice(0, 1))
    setSelectedClients(nextClients)
    setClientSearch('')
    setCreatedCode(null)
  }, [availableProtocolsKey, initialClientsKey, initialProtocolsKey, open, protocolOptions])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setClientsLoading(true)
    void getConfigs(false)
      .then((configs) => {
        if (cancelled) return
        const byName = new Map<string, Set<UnlockCodeProtocol>>()
        for (const config of configs) {
          const name = normalizeClientName(config.client_name)
          const protocol = toUnlockProtocol(config.vpn_type)
          if (!name || !protocol) continue
          const set = byName.get(name) ?? new Set<UnlockCodeProtocol>()
          set.add(protocol)
          byName.set(name, set)
        }
        const options = Array.from(byName.entries())
          .map(([name, protocols]) => ({
            name,
            protocols: ALL_PROTOCOLS.filter((protocol) => protocols.has(protocol)),
          }))
          .sort((a, b) => a.name.localeCompare(b.name, 'ru'))
        setClientOptions(options)
      })
      .catch(() => {
        if (!cancelled) setClientOptions([])
      })
      .finally(() => {
        if (!cancelled) setClientsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open])

  const profileBound = selectedClients.length > 0

  const pickerClientOptions = useMemo(() => {
    // Allow picking a client first (profile key). Filter by protocol only for unrestricted codes.
    if (profileBound || selectedProtocols.length === 0) return clientOptions
    return clientOptions.filter((client) => clientMatchesProtocols(client, selectedProtocols))
  }, [clientOptions, profileBound, selectedProtocols])

  useEffect(() => {
    if (!profileBound) return
    setSelectedProtocols((prev) => {
      const same =
        prev.length === protocolOptions.length && protocolOptions.every((protocol) => prev.includes(protocol))
      return same ? prev : protocolOptions
    })
  }, [profileBound, protocolOptions])

  const filteredClientOptions = useMemo(() => {
    const query = normalizeClientName(clientSearch)
    const selected = new Set(selectedClients)
    return pickerClientOptions.filter((client) => {
      if (selected.has(client.name)) return false
      if (!query) return true
      return client.name.includes(query)
    })
  }, [pickerClientOptions, clientSearch, selectedClients])

  const toggleProtocol = (protocol: UnlockCodeProtocol) => {
    setSelectedProtocols((prev) =>
      prev.includes(protocol) ? prev.filter((item) => item !== protocol) : [...prev, protocol],
    )
  }

  const addClient = (name: string) => {
    const key = normalizeClientName(name)
    if (!key) return
    setSelectedClients((prev) => (prev.includes(key) ? prev : [...prev, key]))
    setClientSearch('')
  }

  const removeClient = (name: string) => {
    setSelectedClients((prev) => prev.filter((item) => item !== name))
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    const parsedGrantDays = Number.parseInt(grantDays, 10)
    if (!Number.isFinite(parsedGrantDays) || parsedGrantDays < 1 || parsedGrantDays > 3650) {
      notifyError('Срок выдачи должен быть от 1 до 3650 дней')
      return
    }
    if (!profileBound && selectedProtocols.length === 0) {
      notifyError('Выберите хотя бы один протокол')
      return
    }
    const parsedMaxRedemptions = Number.parseInt(maxRedemptions, 10)
    if (mode === 'multi' && (!Number.isFinite(parsedMaxRedemptions) || parsedMaxRedemptions < 1)) {
      notifyError('Укажите корректное число активаций')
      return
    }

    setSaving(true)
    try {
      const protocolsForCreate = profileBound
        ? protocolOptions.length > 0
          ? protocolOptions
          : selectedProtocols
        : selectedProtocols
      if (protocolsForCreate.length === 0) {
        notifyError('Выберите хотя бы один протокол')
        setSaving(false)
        return
      }
      const created = await createUnlockCode({
        grant_days: parsedGrantDays,
        protocols: protocolsForCreate,
        mode,
        max_redemptions: mode === 'single' ? 1 : parsedMaxRedemptions,
        code_expires_at: toEndOfDayIso(codeExpiresAt),
        allowed_client_names: selectedClients,
      })
      setCreatedCode(created)
      success('Unlock-ключ создан')
      await onCreated?.(created)
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось создать unlock-ключ')
    } finally {
      setSaving(false)
    }
  }

  const copyCode = async () => {
    if (!createdCode) return
    try {
      await navigator.clipboard.writeText(createdCode.code)
      success('Код скопирован')
    } catch {
      notifyError('Не удалось скопировать код')
    }
  }

  const hasMultiMode = mode === 'multi'
  const clientsHint = profileBound
    ? `${selectedClients.length} проф.`
    : selectedProtocols.length === 0
      ? 'любой / выберите клиента'
      : `любой из ${pickerClientOptions.length}`

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound size={18} />
            Создание unlock-ключа
          </DialogTitle>
          <DialogDescription>
            {profileBound
              ? 'Ключ привязан к профилю клиента: при активации продлевается общий срок по всем протоколам профиля.'
              : 'Без списка клиентов ключ может активировать любой клиент с пересечением по выбранным протоколам.'}
          </DialogDescription>
        </DialogHeader>

        <form className="space-y-4" onSubmit={(event) => void handleSubmit(event)} noValidate>
          {createdCode && (
            <div className="space-y-3 rounded-xl border bg-muted/20 p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">Сгенерированный код</p>
                  <p className="break-all font-mono text-lg font-semibold">{createdCode.code}</p>
                </div>
                <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={copyCode}>
                  <Copy size={14} />
                  Копировать
                </Button>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="secondary">{createdCode.mode === 'multi' ? 'multi' : 'single'}</Badge>
                <Badge variant="outline">{createdCode.grant_days} дн.</Badge>
                <Badge variant="outline">Активаций: {createdCode.max_redemptions}</Badge>
                {(createdCode.allowed_client_names?.length ?? 0) > 0 ? (
                  <Badge variant="outline">Профиль</Badge>
                ) : (
                  createdCode.protocols.map((protocol) => (
                    <Badge key={protocol} variant="outline">
                      {protocolLabel(protocol as UnlockCodeProtocol)}
                    </Badge>
                  ))
                )}
                <Badge variant="outline">
                  {(createdCode.allowed_client_names?.length ?? 0) > 0
                    ? `Клиенты: ${createdCode.allowed_client_names!.join(', ')}`
                    : 'Клиенты: любой'}
                </Badge>
                <Badge variant="outline">До {formatDate(createdCode.code_expires_at)}</Badge>
              </div>
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="unlock-grant-days">Срок продления, дни</Label>
              <Input
                id="unlock-grant-days"
                type="number"
                min={1}
                max={3650}
                value={grantDays}
                onChange={(event) => setGrantDays(event.target.value)}
                autoFocus={!createdCode}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="unlock-code-expires">Срок жизни кода</Label>
              <Input
                id="unlock-code-expires"
                type="date"
                value={codeExpiresAt}
                onChange={(event) => setCodeExpiresAt(event.target.value)}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label>Режим</Label>
            <div className="grid grid-cols-2 gap-2">
              <Button
                type="button"
                variant={mode === 'single' ? 'default' : 'outline'}
                onClick={() => {
                  setMode('single')
                  setMaxRedemptions('1')
                }}
              >
                Single
              </Button>
              <Button
                type="button"
                variant={mode === 'multi' ? 'default' : 'outline'}
                onClick={() => {
                  setMode('multi')
                  if (maxRedemptions === '1') setMaxRedemptions('10')
                }}
              >
                Multi
              </Button>
            </div>
          </div>

          {hasMultiMode && (
            <div className="space-y-2">
              <Label htmlFor="unlock-max-redemptions">Макс. активаций</Label>
              <Input
                id="unlock-max-redemptions"
                type="number"
                min={1}
                max={1000}
                value={maxRedemptions}
                onChange={(event) => setMaxRedemptions(event.target.value)}
              />
            </div>
          )}

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <Label htmlFor="unlock-client-search">Клиенты (опционально)</Label>
              <span className="text-xs text-muted-foreground">{clientsHint}</span>
            </div>
            {selectedClients.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {selectedClients.map((name) => (
                  <Badge key={name} variant="secondary" className="gap-1 pr-1">
                    {name}
                    <button
                      type="button"
                      className="rounded-sm p-0.5 hover:bg-muted"
                      onClick={() => removeClient(name)}
                      aria-label={`Убрать ${name}`}
                    >
                      <X size={12} />
                    </button>
                  </Badge>
                ))}
              </div>
            )}
            {profileBound && (
              <div className="rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-xs text-muted-foreground">
                Ключ привязан к профилю: при активации продлевается общий срок по всем протоколам клиента на
                узле портала.
              </div>
            )}
            <Input
              id="unlock-client-search"
              value={clientSearch}
              onChange={(event) => setClientSearch(event.target.value)}
              placeholder="Поиск клиента…"
              autoComplete="off"
            />
            <div className="max-h-36 overflow-y-auto rounded-lg border bg-muted/10">
              {clientsLoading ? (
                <div className="flex items-center gap-2 px-3 py-3 text-xs text-muted-foreground">
                  <Loader2 size={14} className="animate-spin" />
                  Загрузка клиентов…
                </div>
              ) : filteredClientOptions.length === 0 ? (
                <div className="px-3 py-3 text-xs text-muted-foreground">
                  {clientOptions.length === 0
                    ? 'Нет клиентов для выбора'
                    : 'Ничего не найдено'}
                </div>
              ) : (
                <ul className="divide-y divide-border/60">
                  {filteredClientOptions.slice(0, 40).map((client) => (
                    <li key={client.name}>
                      <button
                        type="button"
                        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-muted/50"
                        onClick={() => addClient(client.name)}
                      >
                        <span className="min-w-0 truncate font-medium">{client.name}</span>
                        <span className="flex shrink-0 flex-wrap justify-end gap-1">
                          {client.protocols.map((protocol) => (
                            <Badge key={protocol} variant="outline" className="px-1.5 py-0 text-[10px]">
                              {shortProtocolLabel(protocol)}
                            </Badge>
                          ))}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {!profileBound && (
            <div className="space-y-2">
              <Label>Протоколы</Label>
              <div className="grid gap-2 sm:grid-cols-3">
                {protocolOptions.map((protocol) => {
                  const checked = selectedProtocols.includes(protocol)
                  return (
                    <button
                      key={protocol}
                      type="button"
                      onClick={() => toggleProtocol(protocol)}
                      className={cn(
                        'rounded-lg border px-3 py-2 text-left text-sm transition-colors',
                        checked ? 'border-primary bg-primary/10 text-primary' : 'hover:bg-muted/50',
                      )}
                    >
                      <span className="block font-medium">{protocolLabel(protocol)}</span>
                      <span className="text-xs text-muted-foreground">{checked ? 'Выбран' : 'Не выбран'}</span>
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          <DialogFooter className="gap-2 sm:gap-0">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
              Закрыть
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? <Loader2 size={14} className="animate-spin" /> : null}
              Создать
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
