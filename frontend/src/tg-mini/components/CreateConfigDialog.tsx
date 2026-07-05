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
import { createTgPanelConfig, applyTgClientTemplate, getTgClientTemplates, getTgPanelUsers } from '@/tg-mini/api'
import type { ClientTemplate, SelfServiceQuota, User, VpnType } from '@/types'

interface CreateConfigDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  isAdmin: boolean
  currentUserId?: number
  openvpnEnabled: boolean
  wireguardEnabled: boolean
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
  quota,
  onCreated,
}: CreateConfigDialogProps) {
  const defaultVpnType = useMemo((): VpnType => {
    if (openvpnEnabled) return 'openvpn'
    if (wireguardEnabled) return 'wireguard'
    return 'openvpn'
  }, [openvpnEnabled, wireguardEnabled])

  const [clientName, setClientName] = useState('')
  const [description, setDescription] = useState('')
  const [vpnType, setVpnType] = useState<VpnType>(defaultVpnType)
  const [certDays, setCertDays] = useState('3650')
  const [ownerId, setOwnerId] = useState<number | null>(currentUserId ?? null)
  const [users, setUsers] = useState<User[]>([])
  const [templates, setTemplates] = useState<ClientTemplate[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [applyingTemplateId, setApplyingTemplateId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setVpnType(defaultVpnType)
    setOwnerId(currentUserId ?? null)
    setError(null)
  }, [open, defaultVpnType, currentUserId])

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
    setVpnType(defaultVpnType)
    setCertDays('3650')
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

  const handleApplyTemplate = async (template: ClientTemplate) => {
    const trimmedName = clientName.trim()
    const nameError = validateClientName(trimmedName)
    if (nameError) {
      setError(nameError)
      return
    }
    setApplyingTemplateId(template.id)
    setError(null)
    try {
      await applyTgClientTemplate(template.id, {
        client_name: trimmedName,
        owner_id: isAdmin && ownerId ? ownerId : undefined,
      })
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
      onCreated()
      handleClose()
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
    const parsedCertDays = Number(certDays)
    if (vpnType === 'openvpn' && (!Number.isFinite(parsedCertDays) || parsedCertDays < 1 || parsedCertDays > 3650)) {
      setError('Срок сертификата: от 1 до 3650 дней')
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      await createTgPanelConfig({
        client_name: trimmedName,
        vpn_type: vpnType,
        cert_expire_days: vpnType === 'openvpn' ? parsedCertDays : undefined,
        description: description.trim() || undefined,
        owner_id: isAdmin && ownerId ? ownerId : undefined,
      })
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
      onCreated()
      handleClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка создания')
    } finally {
      setSubmitting(false)
    }
  }

  const quotaReached = quota != null && !quota.unlimited && !quota.can_create
  const busy = submitting || applyingTemplateId != null

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : handleClose())}>
      <DialogContent className="tg-mini-dialog-sheet tg-mini-config-sheet max-w-lg gap-0 p-0 sm:rounded-t-2xl">
        <div className="tg-mini-sheet-handle" aria-hidden />

        <form onSubmit={(e) => void handleSubmit(e)} className="tg-mini-config-sheet-form">
          <DialogHeader className="shrink-0 space-y-2 px-4 pb-3 pt-2 text-left">
            <DialogTitle className="text-base font-semibold">Новый конфиг</DialogTitle>
            <DialogDescription className="text-xs leading-relaxed">
              Создайте VPN-профиль на активном узле. После создания его можно сразу отправить в Telegram.
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
              <Label htmlFor="tg-mini-client-name">Имя клиента</Label>
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
              <Label htmlFor="tg-mini-vpn-type">Протокол</Label>
              <Select
                value={vpnType}
                onValueChange={(value) => setVpnType(value as VpnType)}
                disabled={busy || quotaReached}
              >
                <SelectTrigger id="tg-mini-vpn-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="z-[100]">
                  {openvpnEnabled && <SelectItem value="openvpn">OpenVPN</SelectItem>}
                  {wireguardEnabled && <SelectItem value="wireguard">WireGuard</SelectItem>}
                </SelectContent>
              </Select>
            </div>

            {vpnType === 'openvpn' && (
              <div className="space-y-2">
                <Label htmlFor="tg-mini-cert-days">Срок сертификата (дней)</Label>
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
                description="Пользователь увидит конфиг в своём списке"
              />
            )}

            {templates.length > 0 && (
              <div className="space-y-2">
                <Label>Шаблоны</Label>
                <p className="text-xs text-muted-foreground">
                  Укажите имя клиента и нажмите шаблон для быстрого создания
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
            <Button type="submit" className="w-full gap-2" size="lg" disabled={busy || quotaReached}>
              {submitting ? <Loader2 size={18} className="animate-spin" aria-hidden /> : <Plus size={18} aria-hidden />}
              Создать
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
