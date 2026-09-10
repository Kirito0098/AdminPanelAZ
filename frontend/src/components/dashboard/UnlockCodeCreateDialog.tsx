import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Copy, KeyRound, Loader2 } from 'lucide-react'
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
import type { UnlockCodeRecord } from '@/types'

const ALL_PROTOCOLS: UnlockCodeProtocol[] = ['openvpn', 'wireguard', 'amneziawg2']

function protocolLabel(protocol: UnlockCodeProtocol) {
  if (protocol === 'openvpn') return 'OpenVPN'
  // One WG access policy covers both portal tabs WireGuard and AmneziaWG (vpn_type=wireguard).
  if (protocol === 'wireguard') return 'WireGuard / AmneziaWG'
  return 'AmneziaWG 2.0'
}

function toEndOfDayIso(value: string) {
  if (!value) return null
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return null
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 23, 59, 59, 999)
  return date.toISOString()
}

interface UnlockCodeCreateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialProtocols?: UnlockCodeProtocol[]
  availableProtocols?: UnlockCodeProtocol[]
  onCreated?: (code: UnlockCodeRecord) => Promise<void> | void
}

export default function UnlockCodeCreateDialog({
  open,
  onOpenChange,
  initialProtocols = ['openvpn'],
  availableProtocols = ALL_PROTOCOLS,
  onCreated,
}: UnlockCodeCreateDialogProps) {
  const { success, error: notifyError } = useNotifications()
  const availableProtocolsKey = availableProtocols.join(',')
  const initialProtocolsKey = initialProtocols.join(',')
  const protocolOptions = useMemo(
    () => ALL_PROTOCOLS.filter((protocol) => availableProtocols.includes(protocol)),
    [availableProtocolsKey],
  )
  const [grantDays, setGrantDays] = useState('30')
  const [mode, setMode] = useState<'single' | 'multi'>('single')
  const [maxRedemptions, setMaxRedemptions] = useState('10')
  const [codeExpiresAt, setCodeExpiresAt] = useState('')
  const [selectedProtocols, setSelectedProtocols] = useState<UnlockCodeProtocol[]>([])
  const [createdCode, setCreatedCode] = useState<UnlockCodeRecord | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    const nextProtocols = initialProtocols.filter((protocol) => protocolOptions.includes(protocol))
    setGrantDays('30')
    setMode('single')
    setMaxRedemptions('10')
    setCodeExpiresAt('')
    setSelectedProtocols(nextProtocols.length > 0 ? nextProtocols : protocolOptions.slice(0, 1))
    setCreatedCode(null)
  }, [availableProtocolsKey, initialProtocolsKey, open, protocolOptions])

  const toggleProtocol = (protocol: UnlockCodeProtocol) => {
    setSelectedProtocols((prev) =>
      prev.includes(protocol) ? prev.filter((item) => item !== protocol) : [...prev, protocol],
    )
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    const parsedGrantDays = Number.parseInt(grantDays, 10)
    if (!Number.isFinite(parsedGrantDays) || parsedGrantDays < 1 || parsedGrantDays > 3650) {
      notifyError('Срок выдачи должен быть от 1 до 3650 дней')
      return
    }
    if (selectedProtocols.length === 0) {
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
      const created = await createUnlockCode({
        grant_days: parsedGrantDays,
        protocols: selectedProtocols,
        mode,
        max_redemptions: mode === 'single' ? 1 : parsedMaxRedemptions,
        code_expires_at: toEndOfDayIso(codeExpiresAt),
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound size={18} />
            Создание unlock-ключа
          </DialogTitle>
          <DialogDescription>
            Сгенерируйте ключ продления для выбранных протоколов и передайте его клиенту.
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
                {createdCode.protocols.map((protocol) => (
                  <Badge key={protocol} variant="outline">
                    {protocolLabel(protocol as UnlockCodeProtocol)}
                  </Badge>
                ))}
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
            <Label>Протоколы</Label>
            <div className="grid gap-2 sm:grid-cols-3">
              {protocolOptions.map((protocol) => {
                const checked = selectedProtocols.includes(protocol)
                return (
                  <button
                    key={protocol}
                    type="button"
                    onClick={() => toggleProtocol(protocol)}
                    className={[
                      'rounded-lg border px-3 py-2 text-left text-sm transition-colors',
                      checked ? 'border-primary bg-primary/10 text-primary' : 'hover:bg-muted/50',
                    ].join(' ')}
                  >
                    <span className="block font-medium">{protocolLabel(protocol)}</span>
                    <span className="text-xs text-muted-foreground">{checked ? 'Выбран' : 'Не выбран'}</span>
                  </button>
                )
              })}
            </div>
          </div>

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
