import { useEffect, useMemo, useState } from 'react'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import type { CidrProviderInfo } from '@/types'

const CUSTOM_PROVIDER_FILENAME = 'custom-ips.txt'

type WizardMode = 'custom' | 'existing'

interface CustomProviderWizardDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  providers: CidrProviderInfo[]
  defaultProviderKey?: string
  loading?: boolean
  onSubmit: (payload: {
    providerKey: string
    cidrs_text: string
    asns_text: string
  }) => Promise<void>
}

function parseAsnLines(text: string): string[] {
  return text
    .split(/[\n,;\s]+/)
    .map((line) => line.trim())
    .filter(Boolean)
}

export default function CustomProviderWizardDialog({
  open,
  onOpenChange,
  providers,
  defaultProviderKey,
  loading,
  onSubmit,
}: CustomProviderWizardDialogProps) {
  const existingProviders = useMemo(
    () => providers.filter((p) => p.filename !== CUSTOM_PROVIDER_FILENAME),
    [providers],
  )
  const [mode, setMode] = useState<WizardMode>('custom')
  const [providerKey, setProviderKey] = useState(
    defaultProviderKey && defaultProviderKey !== CUSTOM_PROVIDER_FILENAME
      ? defaultProviderKey
      : existingProviders[0]?.filename ?? '',
  )
  const [cidrsText, setCidrsText] = useState('')
  const [asnsText, setAsnsText] = useState('')

  useEffect(() => {
    if (!open) return
    setMode('custom')
    setCidrsText('')
    setAsnsText('')
    const fallback =
      defaultProviderKey && defaultProviderKey !== CUSTOM_PROVIDER_FILENAME
        ? defaultProviderKey
        : existingProviders[0]?.filename ?? ''
    setProviderKey(fallback)
  }, [open, defaultProviderKey, existingProviders])

  const cidrCount = useMemo(
    () => cidrsText.split('\n').filter((l) => l.trim() && !l.trim().startsWith('#')).length,
    [cidrsText],
  )
  const asnCount = useMemo(() => parseAsnLines(asnsText).length, [asnsText])

  const resolvedKey = mode === 'custom' ? CUSTOM_PROVIDER_FILENAME : providerKey

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Свои ASN/CIDR"
      description="Записи попадут в SQLite CIDR БД. Затем выполните сборку (этап 2) и deploy — и включите провайдера на вкладке «Провайдеры»."
      confirmLabel="Добавить в БД"
      loading={loading}
      onConfirm={async () => {
        if (!resolvedKey) return
        await onSubmit({
          providerKey: resolvedKey,
          cidrs_text: cidrsText,
          asns_text: asnsText,
        })
        setCidrsText('')
        setAsnsText('')
      }}
    >
      <div className="space-y-4 py-2">
        <div className="space-y-2">
          <Label>Куда добавить</Label>
          <div className="grid gap-2 sm:grid-cols-2">
            <button
              type="button"
              disabled={loading}
              onClick={() => setMode('custom')}
              className={cn(
                'rounded-lg border px-3 py-2.5 text-left transition-colors',
                mode === 'custom'
                  ? 'border-primary bg-primary/10 ring-1 ring-primary'
                  : 'hover:bg-muted/40',
              )}
            >
              <div className="text-sm font-medium">Свой список</div>
              <div className="mt-0.5 text-xs text-muted-foreground">
                Отдельный провайдер «Свой список» ({CUSTOM_PROVIDER_FILENAME})
              </div>
            </button>
            <button
              type="button"
              disabled={loading || existingProviders.length === 0}
              onClick={() => setMode('existing')}
              className={cn(
                'rounded-lg border px-3 py-2.5 text-left transition-colors',
                mode === 'existing'
                  ? 'border-primary bg-primary/10 ring-1 ring-primary'
                  : 'hover:bg-muted/40',
                existingProviders.length === 0 && 'opacity-50',
              )}
            >
              <div className="text-sm font-medium">Дописать к провайдеру</div>
              <div className="mt-0.5 text-xs text-muted-foreground">
                Добавить CIDR/ASN в Akamai, Cloudflare и т.д.
              </div>
            </button>
          </div>
        </div>

        {mode === 'existing' && (
          <div className="space-y-2">
            <Label htmlFor="custom-provider-key">Провайдер</Label>
            <select
              id="custom-provider-key"
              className="flex h-9 w-full rounded-md border bg-background px-3 text-sm"
              value={providerKey}
              onChange={(e) => setProviderKey(e.target.value)}
              disabled={loading}
            >
              {existingProviders.map((p) => (
                <option key={p.filename} value={p.filename}>
                  {p.name} ({p.filename})
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="space-y-2">
          <Label htmlFor="custom-cidrs">CIDR (по одному на строку)</Label>
          <Textarea
            id="custom-cidrs"
            rows={5}
            placeholder={'203.0.113.0/24\n198.51.100.0/24'}
            value={cidrsText}
            onChange={(e) => setCidrsText(e.target.value)}
            disabled={loading}
            className="font-mono text-xs"
          />
          <p className="text-xs text-muted-foreground">Строк: {cidrCount}</p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="custom-asns">ASN (AS12345 или 12345)</Label>
          <Textarea
            id="custom-asns"
            rows={3}
            placeholder={'AS13335\nAS15169'}
            value={asnsText}
            onChange={(e) => setAsnsText(e.target.value)}
            disabled={loading}
            className="font-mono text-xs"
          />
          <p className="text-xs text-muted-foreground">ASN: {asnCount}</p>
        </div>
      </div>
    </ConfirmDialog>
  )
}
