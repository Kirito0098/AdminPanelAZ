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
import { createTgPanelConfig, applyTgClientTemplate, getTgClientTemplates, getTgPanelUsers, setTgClientAccessUntil } from '@/tg-mini/api'
import { AWG2_TTL_OPTIONS } from '@/components/awg2/utils'
import { cn } from '@/lib/utils'
import type { ClientTemplate, SelfServiceQuota, User, VpnType } from '@/types'

const PROTOCOL_ORDER: VpnType[] = ['openvpn', 'wireguard', 'amneziawg2']

function vpnLabel(type: VpnType): string {
  if (type === 'openvpn') return 'OpenVPN'
  if (type === 'wireguard') return 'WG/AWG 1.5'
  return 'AWG 2.0'
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
  const [templates, setTemplates] = useState<ClientTemplate[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [applyingTemplateId, setApplyingTemplateId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setSelectedProtocols(availableProtocols)
    setTtl('none')
    setAccessUntilDate('')
    setOwnerId(currentUserId ?? null)
    setError(null)
  }, [open, availableProtocols, currentUserId])

  useEffect(() => {
    if (!open) return
    void getTgClientTemplates()
      .then(setTemplates)
      .catch(() => setTemplates([]))
  }, [open])

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

  const finishCreate = (accessErr: string | null) => {
    window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
    onCreated()
    handleClose()
    if (accessErr) {
      window.Telegram?.WebApp.showAlert?.(`Клиент создан, но срок доступа не сохранён: ${accessErr}`)
    }
  }

  const toggleProtocol = (type: VpnType) => {
    setSelectedProtocols((prev) =>
      prev.includes(type) ? prev.filter((item) => item !== type) : [...prev, type],
    )
  }

  const handleApplyTemplate = async (template: ClientTemplate) => {
    const trimmedName = clientName.trim()
    const nameError = validateClientName(trimmedName)
    if (nameError) {
      setError(nameError)
      return
    }
    setApplyingTemplateId(template.id)
    setError(null)
    const accessDateSnapshot = accessUntilDate
    try {
      const created = await applyTgClientTemplate(template.id, {
        client_name: trimmedName,
        owner_id: isAdmin && ownerId ? ownerId : undefined,
      })
      const accessErr = await applyAccessUntilAfterCreate(
        trimmedName,
        created.vpn_type,
        accessDateSnapshot,
      )
      finishCreate(accessErr)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка применения шаблона')
    } finally {
      setApplyingTemplateId(null)
    }
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

    setSubmitting(true)
    setError(null)
    const accessDateSnapshot = accessUntilDate
    const ordered = PROTOCOL_ORDER.filter((type) => selectedProtocols.includes(type))
    const created: VpnType[] = []
    let accessErr: string | null = null
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
          if (nextAccessErr) accessErr = nextAccessErr
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
      finishCreate(accessErr)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка создания')
    } finally {
      setSubmitting(false)
    }
  }

  const quotaReached = quota != null && !quota.unlimited && !quota.can_create
  const busy = submitting || applyingTemplateId != null
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

            {templates.length > 0 && (
              <div className="space-y-2">
                <Label>Шаблоны</Label>
                <p className="text-xs text-muted-foreground">
                  Шаблон создаёт одну конфигурацию по пресету
                </p>
                <div className="flex flex-wrap gap-2">
                  {templates.map((template) => (
                    <Button
                      key={template.id}
                      type="button"
                      variant="secondary"
                      size="sm"
                      disabled={busy || quotaReached || !clientName.trim()}
                      onClick={() => void handleApplyTemplate(template)}
                    >
                      {applyingTemplateId === template.id ? (
                        <Loader2 size={14} className="animate-spin" aria-hidden />
                      ) : (
                        template.name
                      )}
                    </Button>
                  ))}
                </div>
              </div>
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
