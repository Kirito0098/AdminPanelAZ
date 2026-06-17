import { useCallback, useEffect, useMemo, useState } from 'react'
import { Network, RefreshCw, RotateCcw, Save } from 'lucide-react'
import {
  getWarperIpRanges,
  saveWarperIpRangesText,
  setWarperIpExport,
  setWarperIpRouteMode,
} from '@/api/client'
import StatusPanel from '@/components/noc/StatusPanel'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
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
import { buildIpRangesTextFromItems, countActiveTextLines, isWarperDisabled } from './utils'

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

  const [savedText, setSavedText] = useState('')
  const [draftText, setDraftText] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [routeMode, setRouteMode] = useState('antizapret')
  const [busy, setBusy] = useState(false)

  const dirty = draftText !== savedText
  const rangeCount = useMemo(() => countActiveTextLines(draftText), [draftText])

  const load = useCallback(async () => {
    if (!health?.installed) {
      setSavedText('')
      setDraftText('')
      setLoading(false)
      setLoadError(null)
      return
    }
    setLoading(true)
    setLoadError(null)
    try {
      const data = await getWarperIpRanges()
      const content = data.content?.trim() || buildIpRangesTextFromItems(data.ranges ?? [])
      setSavedText(content)
      setDraftText(content)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Не удалось загрузить подсети'
      setLoadError(message)
      notifyError(message)
    } finally {
      setLoading(false)
    }
  }, [health?.installed, notifyError])

  useEffect(() => {
    void load()
  }, [load, activeNode?.id, health?.installed])

  async function handleSave() {
    if (!dirty) return
    setSaving(true)
    try {
      const result = await saveWarperIpRangesText(draftText)
      setSavedText(draftText)
      success(result.message ?? 'Подсети сохранены')
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось сохранить подсети')
    } finally {
      setSaving(false)
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

  if (loading && !savedText) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {loadError && <EmptyState title="Ошибка загрузки" description={loadError} />}

      <StatusPanel title="IP-подсети" icon={Network}>
        <p className="mb-4 text-sm text-muted-foreground">
          CIDR-маршруты через sing-box. Редактируйте текстовый файл и сохраните одной кнопкой — валидация и
          синхронизация выполняются на сервере.
        </p>

        <div className="mb-4 flex flex-wrap items-end gap-2">
          <div className="min-w-[220px] flex-1">
            <label className="mb-1 block text-xs text-muted-foreground">Режим маршрутизации</label>
            <Select value={routeMode} onValueChange={setRouteMode} disabled={disabled || busy || saving}>
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
          <Button variant="secondary" size="sm" disabled={disabled || busy || saving} onClick={() => void handleModeApply()}>
            Применить режим
          </Button>
          <Button variant="outline" size="sm" disabled={disabled || busy || saving} onClick={() => void handleExport(true)}>
            Экспорт в AZ
          </Button>
          <Button variant="outline" size="sm" disabled={disabled || busy || saving} onClick={() => void handleExport(false)}>
            Выкл. экспорт
          </Button>
        </div>

        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Badge variant="secondary">Подсетей: {rangeCount}</Badge>
          {dirty && <Badge variant="warning">Есть несохранённые изменения</Badge>}
          {disabled && <Badge variant="warning">Только просмотр</Badge>}
        </div>

        <Textarea
          value={draftText}
          onChange={(e) => setDraftText(e.target.value)}
          disabled={disabled || saving}
          spellCheck={false}
          className="min-h-[16rem] resize-y font-mono text-xs leading-relaxed"
          placeholder={'# IP-подсети\n91.108.4.0/22\n2001:db8::/32'}
        />

        <div className="mt-4 flex flex-wrap gap-2">
          <Button disabled={disabled || saving || !dirty} onClick={() => void handleSave()}>
            <Save className="mr-1.5 h-4 w-4" />
            {saving ? 'Сохранение…' : 'Сохранить'}
          </Button>
          <Button
            variant="outline"
            disabled={disabled || saving || !dirty}
            onClick={() => setDraftText(savedText)}
          >
            <RotateCcw className="mr-1.5 h-4 w-4" />
            Сбросить
          </Button>
          <Button variant="secondary" size="sm" disabled={loading || saving} onClick={() => void load()}>
            <RefreshCw className="mr-1.5 h-4 w-4" />
            Обновить
          </Button>
        </div>
      </StatusPanel>
    </div>
  )
}
