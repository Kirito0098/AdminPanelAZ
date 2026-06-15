import { useMemo, useState } from 'react'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import type { CidrProviderInfo } from '@/types'

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
  const [providerKey, setProviderKey] = useState(defaultProviderKey ?? providers[0]?.filename ?? '')
  const [cidrsText, setCidrsText] = useState('')
  const [asnsText, setAsnsText] = useState('')

  const cidrCount = useMemo(
    () => cidrsText.split('\n').filter((l) => l.trim() && !l.trim().startsWith('#')).length,
    [cidrsText],
  )
  const asnCount = useMemo(() => parseAsnLines(asnsText).length, [asnsText])

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Добавить свои ASN/CIDR"
      description="Записи будут добавлены в SQLite CIDR БД для выбранного провайдера. После этого выполните сборку (этап 2) и deploy."
      confirmLabel="Добавить в БД"
      loading={loading}
      onConfirm={async () => {
        await onSubmit({
          providerKey,
          cidrs_text: cidrsText,
          asns_text: asnsText,
        })
        setCidrsText('')
        setAsnsText('')
      }}
    >
      <div className="space-y-4 py-2">
        <div className="space-y-2">
          <Label htmlFor="custom-provider-key">Провайдер</Label>
          <select
            id="custom-provider-key"
            className="flex h-9 w-full rounded-md border bg-background px-3 text-sm"
            value={providerKey}
            onChange={(e) => setProviderKey(e.target.value)}
            disabled={loading}
          >
            {providers.map((p) => (
              <option key={p.filename} value={p.filename}>
                {p.name} ({p.filename})
              </option>
            ))}
          </select>
        </div>

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
