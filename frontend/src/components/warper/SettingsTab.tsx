import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, Settings2 } from 'lucide-react'
import {
  getWarperMode,
  getWarperSettingsOptions,
  postWarperSingbox,
  setWarperFullVpn,
  setWarperLogLevel,
  setWarperModeSlave,
  setWarperModeWarp,
  setWarperModeWg,
  setWarperMtu,
  setWarperSubnet,
} from '@/api/client'
import StatusPanel from '@/components/noc/StatusPanel'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
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
const WARP_KEY_SOURCES = [
  { value: 'auto', label: 'Автовыбор ключа' },
  { value: 'system', label: 'Ключи AntiZapret' },
  { value: 'generate', label: 'Новый ключ WARP' },
] as const

interface SettingsTabProps {
  health: WarperHealthResponse | null
}

export default function SettingsTab({ health }: SettingsTabProps) {
  const { activeNode } = useNode()
  const { success, error: notifyError } = useNotifications()
  const disabled = isWarperDisabled(health)

  const [mode, setMode] = useState<Record<string, unknown>>({})
  const [warpKeys, setWarpKeys] = useState<string[]>([])
  const [wgConfigs, setWgConfigs] = useState<string[]>([])
  const [mtu, setMtu] = useState('1420')
  const [logLevel, setLogLevel] = useState<string>('info')
  const [subnet, setSubnet] = useState('')
  const [fullVpn, setFullVpn] = useState(false)
  const [warpKeySource, setWarpKeySource] = useState<(typeof WARP_KEY_SOURCES)[number]['value']>('auto')
  const [slaveHost, setSlaveHost] = useState('')
  const [slavePort, setSlavePort] = useState('8444')
  const [slaveKey, setSlaveKey] = useState('')
  const [wgConfigPath, setWgConfigPath] = useState('')
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
      const [modeResponse, optionsResponse] = await Promise.all([
        getWarperMode(),
        getWarperSettingsOptions(),
      ])
      const modeData = modeResponse.mode ?? {}
      setMode(modeData)
      setWarpKeys(optionsResponse.warp_keys ?? [])
      const configs = optionsResponse.wg_configs ?? []
      setWgConfigs(configs)
      if (typeof modeData.mtu === 'number') setMtu(String(modeData.mtu))
      if (typeof modeData.log_level === 'string') setLogLevel(modeData.log_level)
      if (typeof modeData.subnet === 'string') setSubnet(modeData.subnet)
      if (typeof modeData.fullvpn === 'boolean') setFullVpn(modeData.fullvpn)
      if (configs.length > 0) {
        setWgConfigPath((current) => (current && configs.includes(current) ? current : configs[0]))
      }
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

  async function applyWarpMode() {
    setBusy(true)
    try {
      const keySource = warpKeySource === 'auto' ? null : warpKeySource
      const result = await setWarperModeWarp(keySource)
      success(result.message ?? 'Режим WARP применён')
      await load()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось переключить WARP')
    } finally {
      setBusy(false)
    }
  }

  async function applySlaveMode() {
    const port = Number(slavePort)
    if (!slaveHost.trim() || !slaveKey.trim() || !Number.isFinite(port)) return
    setBusy(true)
    try {
      const result = await setWarperModeSlave(slaveHost.trim(), port, slaveKey.trim())
      success(result.message ?? 'Режим Slave применён')
      await load()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось переключить Slave')
    } finally {
      setBusy(false)
    }
  }

  async function applyWgMode() {
    if (!wgConfigPath.trim()) return
    setBusy(true)
    try {
      const result = await setWarperModeWg(wgConfigPath.trim())
      success(result.message ?? 'Режим WireGuard применён')
      await load()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось переключить WireGuard')
    } finally {
      setBusy(false)
    }
  }

  async function saveFullVpn(enable: boolean) {
    setBusy(true)
    try {
      const result = await setWarperFullVpn(enable)
      setFullVpn(enable)
      success(result.message ?? `FullVPN ${enable ? 'включён' : 'выключен'}`)
      await load()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось изменить FullVPN')
    } finally {
      setBusy(false)
    }
  }

  async function saveSubnet() {
    if (!subnet.trim()) return
    setBusy(true)
    try {
      const result = await setWarperSubnet(subnet.trim())
      success(result.message ?? 'Подсеть обновлена')
      await load()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось сохранить подсеть')
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

  const outboundMode =
    typeof mode.outbound_mode === 'string'
      ? mode.outbound_mode
      : typeof mode.mode === 'string'
        ? mode.mode
        : null

  return (
    <div className="space-y-4">
      <StatusPanel title="Настройки AZ-WARP" icon={Settings2}>
        {outboundMode && (
          <div className="mb-4 rounded-lg border bg-muted/20 px-3 py-2 text-sm">
            Текущий режим: <strong>{formatOutboundMode(outboundMode)}</strong>
          </div>
        )}

        <div className="mb-6 space-y-4 rounded-lg border p-4">
          <div>
            <label className="text-sm font-medium">Режим WARP</label>
            <p className="mb-3 text-xs text-muted-foreground">
              Cloudflare WARP с автовыбором или указанным источником ключей.
            </p>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <div className="min-w-[220px] flex-1">
                <Select
                  value={warpKeySource}
                  onValueChange={(value) =>
                    setWarpKeySource(value as (typeof WARP_KEY_SOURCES)[number]['value'])
                  }
                  disabled={disabled || busy}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {WARP_KEY_SOURCES.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button disabled={disabled || busy} onClick={() => void applyWarpMode()}>
                Применить WARP
              </Button>
            </div>
            {warpKeys.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {warpKeys.map((key) => (
                  <Badge key={key} variant="outline" className="font-mono text-xs">
                    {key}
                  </Badge>
                ))}
              </div>
            )}
          </div>

          <div className="border-t pt-4">
            <label className="text-sm font-medium">Режим Slave</label>
            <p className="mb-3 text-xs text-muted-foreground">Маршрутизация через донор-сервер Shadowsocks.</p>
            <div className="grid gap-2 sm:grid-cols-3">
              <Input
                placeholder="1.2.3.4"
                value={slaveHost}
                disabled={disabled || busy}
                onChange={(e) => setSlaveHost(e.target.value)}
              />
              <Input
                type="number"
                placeholder="8444"
                value={slavePort}
                disabled={disabled || busy}
                onChange={(e) => setSlavePort(e.target.value)}
              />
              <Input
                placeholder="ss-key"
                value={slaveKey}
                disabled={disabled || busy}
                onChange={(e) => setSlaveKey(e.target.value)}
              />
            </div>
            <Button className="mt-3" variant="secondary" disabled={disabled || busy} onClick={() => void applySlaveMode()}>
              Применить Slave
            </Button>
          </div>

          <div className="border-t pt-4">
            <label className="text-sm font-medium">Режим WireGuard</label>
            <p className="mb-3 text-xs text-muted-foreground">Собственный WG-конфиг из /root/ или /root/warper/.</p>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
              {wgConfigs.length > 0 ? (
                <Select value={wgConfigPath} onValueChange={setWgConfigPath} disabled={disabled || busy}>
                  <SelectTrigger className="flex-1">
                    <SelectValue placeholder="Выберите .conf" />
                  </SelectTrigger>
                  <SelectContent>
                    {wgConfigs.map((path) => (
                      <SelectItem key={path} value={path}>
                        {path}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  className="flex-1 font-mono text-sm"
                  placeholder="/root/vpn.conf"
                  value={wgConfigPath}
                  disabled={disabled || busy}
                  onChange={(e) => setWgConfigPath(e.target.value)}
                />
              )}
              <Button disabled={disabled || busy} onClick={() => void applyWgMode()}>
                Применить WG
              </Button>
            </div>
          </div>
        </div>

        <div className="mb-6 grid gap-4 md:grid-cols-2">
          <div className="space-y-3 rounded-lg border p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium">FullVPN</div>
                <div className="text-xs text-muted-foreground">Полный VPN-туннель через AZ-WARP</div>
              </div>
              <Switch
                checked={fullVpn}
                disabled={disabled || busy}
                onCheckedChange={(checked) => void saveFullVpn(checked)}
              />
            </div>
          </div>

          <div className="space-y-2 rounded-lg border p-4">
            <label className="text-sm font-medium">Подсеть WARP</label>
            <div className="flex gap-2">
              <Input
                placeholder="172.16.0.0/24"
                value={subnet}
                disabled={disabled || busy}
                onChange={(e) => setSubnet(e.target.value)}
              />
              <Button disabled={disabled || busy} onClick={() => void saveSubnet()}>
                Сохранить
              </Button>
            </div>
          </div>
        </div>

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
