import { useCallback, useEffect, useState } from 'react'
import { Network, Plus, RefreshCw, Trash2 } from 'lucide-react'
import {
  addWarperIpRange,
  getWarperIpRanges,
  removeWarperIpRange,
  setWarperIpExport,
  setWarperIpRouteMode,
  syncWarperIpRanges,
} from '@/api/client'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import StatusPanel from '@/components/noc/StatusPanel'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import type { WarperHealthResponse } from '@/types'
import { cidrLabel, isWarperDisabled } from './utils'

const ROUTE_MODES = [
  { value: 'antizapret', label: 'Только AntiZapret' },
  { value: 'all_vpn', label: 'Весь VPN' },
  { value: 'all', label: 'Весь трафик узла' },
] as const

interface IpRangesTabProps {
  health: WarperHealthResponse | null
}

export default function IpRangesTab({ health }: IpRangesTabProps) {
  const { activeNode } = useNode()
  const { success, error: notifyError } = useNotifications()
  const disabled = isWarperDisabled(health)

  const [ranges, setRanges] = useState<Array<string | Record<string, unknown>>>([])
  const [loading, setLoading] = useState(true)
  const [newCidr, setNewCidr] = useState('')
  const [routeMode, setRouteMode] = useState('antizapret')
  const [busy, setBusy] = useState(false)
  const [removeTarget, setRemoveTarget] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getWarperIpRanges()
      setRanges(data.ranges ?? [])
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось загрузить подсети')
    } finally {
      setLoading(false)
    }
  }, [notifyError])

  useEffect(() => {
    void load()
  }, [load, activeNode?.id])

  async function handleAdd() {
    const value = newCidr.trim()
    if (!value) return
    setBusy(true)
    try {
      await addWarperIpRange(value)
      success(`Подсеть ${value} добавлена`)
      setNewCidr('')
      await load()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось добавить подсеть')
    } finally {
      setBusy(false)
    }
  }

  async function handleSync() {
    setBusy(true)
    try {
      await syncWarperIpRanges()
      success('Подсети синхронизированы. OVPN — переподключение; WG/AWG — обновите конфиг.')
      await load()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось синхронизировать')
    } finally {
      setBusy(false)
    }
  }

  async function handleModeApply() {
    setBusy(true)
    try {
      await setWarperIpRouteMode(routeMode)
      success('Режим маршрутизации подсетей обновлён')
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось применить режим')
    } finally {
      setBusy(false)
    }
  }

  async function handleExport(enable: boolean) {
    setBusy(true)
    try {
      await setWarperIpExport(enable)
      success(enable ? 'Экспорт в AntiZapret включён' : 'Экспорт в AntiZapret выключен')
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось изменить экспорт')
    } finally {
      setBusy(false)
    }
  }

  async function confirmRemove() {
    if (!removeTarget) return
    setBusy(true)
    try {
      await removeWarperIpRange(removeTarget)
      success(`Подсеть ${removeTarget} удалена`)
      setRemoveTarget(null)
      await load()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось удалить подсеть')
    } finally {
      setBusy(false)
    }
  }

  if (loading && ranges.length === 0) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <StatusPanel title="IP-подсети" icon={Network}>
        <p className="mb-4 text-sm text-muted-foreground">
          CIDR-маршруты через sing-box. После изменений выполните синхронизацию.
        </p>

        <div className="mb-4 flex flex-col gap-2 sm:flex-row">
          <Input
            placeholder="91.108.4.0/22"
            value={newCidr}
            disabled={disabled || busy}
            onChange={(e) => setNewCidr(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void handleAdd()}
          />
          <Button disabled={disabled || busy || !newCidr.trim()} onClick={() => void handleAdd()}>
            <Plus className="mr-1.5 h-4 w-4" />
            Добавить
          </Button>
        </div>

        <div className="mb-4 flex flex-wrap items-end gap-2">
          <div className="min-w-[220px] flex-1">
            <label className="mb-1 block text-xs text-muted-foreground">Режим маршрутизации</label>
            <Select value={routeMode} onValueChange={setRouteMode} disabled={disabled || busy}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROUTE_MODES.map((mode) => (
                  <SelectItem key={mode.value} value={mode.value}>
                    {mode.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button variant="secondary" size="sm" disabled={disabled || busy} onClick={() => void handleModeApply()}>
            Применить режим
          </Button>
          <Button variant="outline" size="sm" disabled={disabled || busy} onClick={() => void handleExport(true)}>
            Экспорт в AZ
          </Button>
          <Button variant="outline" size="sm" disabled={disabled || busy} onClick={() => void handleExport(false)}>
            Выкл. экспорт
          </Button>
          <Button size="sm" disabled={disabled || busy} onClick={() => void handleSync()}>
            Синхронизировать
          </Button>
          <Button variant="ghost" size="sm" disabled={loading} onClick={() => void load()}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>

        <Badge variant="secondary" className="mb-3">
          Подсетей: {ranges.length}
        </Badge>

        {ranges.length === 0 ? (
          <EmptyState title="Нет подсетей" description="Добавьте CIDR для маршрутизации через AZ-WARP." />
        ) : (
          <div className="flex flex-wrap gap-2">
            {ranges.map((item) => {
              const label = cidrLabel(item)
              return (
                <div
                  key={label}
                  className="flex items-center gap-1 rounded-md border bg-muted/30 px-2 py-1 font-mono text-sm"
                >
                  {label}
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    disabled={disabled || busy}
                    onClick={() => setRemoveTarget(label)}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                  </Button>
                </div>
              )
            })}
          </div>
        )}
      </StatusPanel>

      <ConfirmDialog
        open={Boolean(removeTarget)}
        title="Удалить подсеть?"
        description={removeTarget ? `CIDR ${removeTarget} будет удалён.` : ''}
        confirmLabel="Удалить"
        destructive
        loading={busy}
        onConfirm={() => void confirmRemove()}
        onOpenChange={(open) => !open && setRemoveTarget(null)}
      />
    </div>
  )
}
