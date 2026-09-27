import { useCallback, useEffect, useId, useState } from 'react'
import { ApiError, getDnsAaaa, setDnsAaaa } from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useNotifications } from '@/context/NotificationContext'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { createLatestRequest } from '@/lib/latestRequest'
import type { DnsAaaaState, DnsAaaaTarget } from '@/types'

const TARGETS: Array<{ id: DnsAaaaTarget; label: string; resolver: string; file: string }> = [
  { id: 'antizapret', label: 'AntiZapret', resolver: 'kresd@1', file: 'custom.lua' },
  { id: 'vpn', label: 'Полный VPN', resolver: 'kresd@2', file: 'custom2.lua' },
]

export type DnsAaaaCardProps = {
  activeNodeId: number | null
  disabled?: boolean
}

export default function DnsAaaaCard({ activeNodeId, disabled = false }: DnsAaaaCardProps) {
  const { success, error: notifyError } = useNotifications()
  const { confirm, dialogProps } = useConfirmDialog()
  const idBase = useId()
  const [state, setState] = useState<DnsAaaaState | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [requests] = useState(() => createLatestRequest<number | null>(null))

  const load = useCallback(async () => {
    requests.reset(activeNodeId)
    setState(null)
    setLoadError(null)
    setLoading(false)
    if (activeNodeId == null) return
    const isCurrent = requests.begin()
    setLoading(true)
    try {
      const data = await getDnsAaaa()
      if (isCurrent()) setState(data)
    } catch (err) {
      if (!isCurrent()) return
      setLoadError(err instanceof ApiError ? err.message : 'Не удалось прочитать настройки DNS')
    } finally {
      if (isCurrent()) setLoading(false)
    }
  }, [activeNodeId, requests])

  useEffect(() => {
    void load()
  }, [load])

  function askToggle(target: (typeof TARGETS)[number], nodata: boolean) {
    confirm({
      title: nodata ? `${target.label}: отвечать NODATA на AAAA?` : `${target.label}: вернуть ответ :: на AAAA?`,
      description: `DNS-резолвер ${target.resolver} перезапустится — несколько секунд клиенты не смогут разрешать имена.`,
      confirmLabel: nodata ? 'Включить NODATA' : 'Вернуть ::',
      onConfirm: async () => {
        const isCurrent = requests.begin()
        setSaving(true)
        try {
          const updated = await setDnsAaaa(target.id, nodata)
          success(`${target.label}: ${nodata ? 'AAAA отвечает NODATA' : 'AAAA отвечает ::'}`)
          if (isCurrent()) setState(updated)
        } catch (err) {
          notifyError(err instanceof ApiError ? err.message : 'Не удалось изменить ответ на AAAA')
          if (isCurrent() && err instanceof ApiError && err.status === 409) void load()
        } finally {
          setSaving(false)
        }
      },
    })
  }

  const controlsDisabled = disabled || loading || saving || state == null

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">DNS: ответ на AAAA</CardTitle>
        <CardDescription className="mt-1">
          AntiZapret на AAAA-запросы отвечает <code>::</code>, и часть клиентов пытается подключиться к себе самой —
          например, Spotify через Music Assistant. NODATA сообщает клиенту, что IPv6-адреса нет, и он идёт по IPv4.
          Утечек IPv6 не добавляет. Действует на всех клиентов (OpenVPN, WireGuard, AmneziaWG) и сохраняется после
          setup.sh.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 border-t px-4 py-4 sm:px-5">
        {activeNodeId == null && (
          <p className="text-xs text-muted-foreground">Выберите VPN-узел вверху, чтобы настроить ответ на AAAA.</p>
        )}

        {loadError && activeNodeId != null && (
          <div className="space-y-3">
            <SettingsAlert variant="danger" title="Не удалось прочитать настройки DNS">
              {loadError}
            </SettingsAlert>
            <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void load()}>
              Повторить загрузку
            </Button>
          </div>
        )}

        {activeNodeId != null &&
          !loadError &&
          TARGETS.map((target) => {
            const mode = state?.[target.id]
            const switchId = `${idBase}-${target.id}`
            const hintId = `${switchId}-hint`
            return (
              <div
                key={target.id}
                className="flex flex-col gap-3 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0 space-y-1">
                  <Label htmlFor={switchId} className="cursor-pointer font-medium">
                    {target.label}: NODATA вместо ::
                  </Label>
                  <p id={hintId} className="text-xs text-muted-foreground">
                    {mode === 'custom'
                      ? `Блок в ${target.file} изменён вручную — поправьте его в Редакторе файлов → DNS`
                      : `${target.resolver}, файл /etc/knot-resolver/${target.file}`}
                  </p>
                </div>
                <Switch
                  id={switchId}
                  aria-describedby={hintId}
                  checked={mode === 'nodata'}
                  disabled={controlsDisabled || mode === 'custom'}
                  onCheckedChange={(checked) => askToggle(target, checked)}
                />
              </div>
            )
          })}
      </CardContent>
      <ConfirmDialogHost dialogProps={dialogProps} />
    </Card>
  )
}
