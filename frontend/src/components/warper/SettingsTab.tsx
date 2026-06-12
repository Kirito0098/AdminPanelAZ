import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, Settings2 } from 'lucide-react'
import {
  getWarperMode,
  postWarperSingbox,
  setWarperLogLevel,
  setWarperMtu,
} from '@/api/client'
import StatusPanel from '@/components/noc/StatusPanel'
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
import { formatOutboundMode, isWarperDisabled } from './utils'

const LOG_LEVELS = ['debug', 'info', 'warn', 'error'] as const

interface SettingsTabProps {
  health: WarperHealthResponse | null
}

export default function SettingsTab({ health }: SettingsTabProps) {
  const { activeNode } = useNode()
  const { success, error: notifyError } = useNotifications()
  const disabled = isWarperDisabled(health)

  const [mode, setMode] = useState<Record<string, unknown>>({})
  const [mtu, setMtu] = useState('1420')
  const [logLevel, setLogLevel] = useState<string>('info')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    if (!health?.installed) {
      setMode({})
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const response = await getWarperMode()
      const modeData = response.mode ?? {}
      setMode(modeData)
      if (typeof modeData.mtu === 'number') setMtu(String(modeData.mtu))
      if (typeof modeData.log_level === 'string') setLogLevel(modeData.log_level)
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось загрузить настройки')
    } finally {
      setLoading(false)
    }
  }, [health?.installed, notifyError])

  useEffect(() => {
    void load()
  }, [load, activeNode?.id])

  async function runSingbox(action: 'start' | 'stop' | 'restart') {
    setBusy(true)
    try {
      const result = await postWarperSingbox(action)
      success(result.message ?? `sing-box: ${action}`)
      await load()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Ошибка sing-box')
    } finally {
      setBusy(false)
    }
  }

  async function saveMtu() {
    const value = Number(mtu)
    if (!Number.isFinite(value)) return
    setBusy(true)
    try {
      await setWarperMtu(value)
      success(`MTU установлен: ${value}`)
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось сохранить MTU')
    } finally {
      setBusy(false)
    }
  }

  async function saveLogLevel() {
    setBusy(true)
    try {
      await setWarperLogLevel(logLevel)
      success(`Уровень логов: ${logLevel}`)
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось сохранить уровень логов')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    )
  }

  const outboundMode = typeof mode.outbound_mode === 'string' ? mode.outbound_mode : null

  return (
    <div className="space-y-4">
      <StatusPanel title="Настройки AZ-WARP" icon={Settings2}>
        {outboundMode && (
          <div className="mb-4 rounded-lg border bg-muted/20 px-3 py-2 text-sm">
            Режим маршрутизации: <strong>{formatOutboundMode(outboundMode)}</strong>
          </div>
        )}

        <div className="grid gap-6 md:grid-cols-2">
          <div className="space-y-2 rounded-lg border p-4">
            <label className="text-sm font-medium">MTU sing-box</label>
            <div className="flex gap-2">
              <Input
                type="number"
                min={1280}
                max={1500}
                value={mtu}
                disabled={disabled || busy}
                onChange={(e) => setMtu(e.target.value)}
              />
              <Button disabled={disabled || busy} onClick={() => void saveMtu()}>
                Сохранить
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">Рекомендуется 1280–1500.</p>
          </div>

          <div className="space-y-2 rounded-lg border p-4">
            <label className="text-sm font-medium">Уровень логов</label>
            <div className="flex gap-2">
              <Select value={logLevel} onValueChange={setLogLevel} disabled={disabled || busy}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {LOG_LEVELS.map((level) => (
                    <SelectItem key={level} value={level}>
                      {level}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button disabled={disabled || busy} onClick={() => void saveLogLevel()}>
                Сохранить
              </Button>
            </div>
          </div>
        </div>

        <div className="mt-6 space-y-2 rounded-lg border p-4">
          <label className="text-sm font-medium">Управление sing-box</label>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" disabled={disabled || busy} onClick={() => void runSingbox('start')}>
              Старт
            </Button>
            <Button size="sm" variant="secondary" disabled={disabled || busy} onClick={() => void runSingbox('stop')}>
              Стоп
            </Button>
            <Button size="sm" disabled={disabled || busy} onClick={() => void runSingbox('restart')}>
              <RefreshCw className="mr-1.5 h-4 w-4" />
              Перезапуск
            </Button>
          </div>
        </div>
      </StatusPanel>
    </div>
  )
}
