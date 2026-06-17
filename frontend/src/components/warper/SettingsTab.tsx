import { useCallback, useEffect, useState } from 'react'
import {
  Cloud,
  Gauge,
  Network,
  Play,
  RefreshCw,
  Server,
  Settings2,
  Shield,
  Square,
  RotateCw,
} from 'lucide-react'
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
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
import { cn } from '@/lib/utils'
import WarperSection, { WarperStatTile } from './WarperSection'
import {
  formatOutboundMode,
  isWarperDisabled,
  normalizeOutboundMode,
  OUTBOUND_MODE_OPTIONS,
  WARP_KEY_SOURCES,
  type WarperOutboundMode,
} from './utils'

const LOG_LEVELS = ['debug', 'info', 'warn', 'error'] as const

function warpKeyBasename(path: string): string {
  const parts = path.split('/').filter(Boolean)
  return parts[parts.length - 1] ?? path
}

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
  const [modeDraft, setModeDraft] = useState<WarperOutboundMode>('warp')
  const [slaveHost, setSlaveHost] = useState('')
  const [slavePort, setSlavePort] = useState('8444')
  const [slaveKey, setSlaveKey] = useState('')
  const [wgConfigPath, setWgConfigPath] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const currentMode = normalizeOutboundMode(mode.outbound_mode ?? mode.mode)

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
      const active = normalizeOutboundMode(modeData.outbound_mode ?? modeData.mode)
      if (active) setModeDraft(active)
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
        <Spinner label="Загрузка настроек AZ-WARP..." />
      </div>
    )
  }

  const modeIcons = { warp: Cloud, slave: Server, wg: Shield } as const

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-lg border bg-muted/20 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Settings2 className="h-4 w-4 text-primary" />
            Настройки AZ-WARP
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Режим выхода, сеть и параметры sing-box на активном узле.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {currentMode && (
            <Badge variant="secondary">Сейчас: {formatOutboundMode(currentMode)}</Badge>
          )}
          {disabled && <Badge variant="warning">Только просмотр</Badge>}
          <Button variant="secondary" size="sm" disabled={busy} onClick={() => void load()}>
            <RefreshCw className="mr-1.5 h-4 w-4" />
            Обновить
          </Button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <WarperStatTile
          label="Режим выхода"
          value={formatOutboundMode(currentMode)}
          hint="Активная конфигурация WARP / Slave / WG"
        />
        <WarperStatTile label="MTU sing-box" value={mtu} hint="1280–1500" />
        <WarperStatTile label="Уровень логов" value={logLevel} />
        <WarperStatTile label="FullVPN" value={fullVpn ? 'Включён' : 'Выключен'} />
      </div>

      <WarperSection
        title="Режим выхода"
        icon={Cloud}
        description="Выберите способ маршрутизации трафика и настройте параметры"
      >
        <div className="grid gap-3 md:grid-cols-3">
          {OUTBOUND_MODE_OPTIONS.map((option) => {
            const Icon = modeIcons[option.id]
            const selected = modeDraft === option.id
            const active = currentMode === option.id
            return (
              <button
                key={option.id}
                type="button"
                disabled={disabled || busy}
                onClick={() => setModeDraft(option.id)}
                className={cn(
                  'rounded-lg border p-4 text-left transition-colors',
                  selected ? 'border-primary bg-primary/5 ring-1 ring-primary/30' : 'hover:bg-muted/30',
                  disabled && 'opacity-60',
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="flex h-9 w-9 items-center justify-center rounded-md bg-muted">
                    <Icon className="h-4 w-4" />
                  </span>
                  {active && <Badge variant="success">Активен</Badge>}
                </div>
                <div className="mt-3 font-medium">{option.label}</div>
                <p className="mt-1 text-xs text-muted-foreground">{option.description}</p>
              </button>
            )
          })}
        </div>

        <div className="mt-4 rounded-lg border bg-muted/10 p-4">
          {modeDraft === 'warp' && (
            <div className="space-y-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div className="min-w-0 flex-1 space-y-2">
                  <Label htmlFor="warp-key-source">Источник WARP-ключа</Label>
                  <Select
                    value={warpKeySource}
                    onValueChange={(value) =>
                      setWarpKeySource(value as (typeof WARP_KEY_SOURCES)[number]['value'])
                    }
                    disabled={disabled || busy}
                  >
                    <SelectTrigger id="warp-key-source" className="w-full lg:max-w-sm">
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
                  <p className="text-xs text-muted-foreground">
                    {WARP_KEY_SOURCES.find((item) => item.value === warpKeySource)?.description}
                  </p>
                </div>
                <Button
                  className="w-full shrink-0 lg:w-auto"
                  disabled={disabled || busy}
                  onClick={() => void applyWarpMode()}
                >
                  Применить WARP
                </Button>
              </div>

              {warpKeys.length > 0 && (
                <div className="rounded-md border bg-background/40 px-3 py-2.5">
                  <p className="mb-2 text-xs font-medium text-muted-foreground">
                    Конфиги на узле ({warpKeys.length})
                  </p>
                  <ul className="grid gap-2 sm:grid-cols-2">
                    {warpKeys.map((key) => (
                      <li
                        key={key}
                        className="flex min-w-0 items-start gap-2 rounded-md border bg-muted/20 px-2.5 py-2"
                      >
                        <Cloud className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary/70" />
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium">{warpKeyBasename(key)}</div>
                          <div className="truncate font-mono text-[11px] text-muted-foreground" title={key}>
                            {key}
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {modeDraft === 'slave' && (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="space-y-1.5">
                  <Label htmlFor="slave-host">Host</Label>
                  <Input
                    id="slave-host"
                    placeholder="1.2.3.4"
                    value={slaveHost}
                    disabled={disabled || busy}
                    onChange={(e) => setSlaveHost(e.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="slave-port">Port</Label>
                  <Input
                    id="slave-port"
                    type="number"
                    placeholder="8444"
                    value={slavePort}
                    disabled={disabled || busy}
                    onChange={(e) => setSlavePort(e.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="slave-key">SS-key</Label>
                  <Input
                    id="slave-key"
                    placeholder="ss-key"
                    value={slaveKey}
                    disabled={disabled || busy}
                    onChange={(e) => setSlaveKey(e.target.value)}
                  />
                </div>
              </div>
              <div className="flex justify-end">
                <Button
                  className="w-full sm:w-auto"
                  disabled={disabled || busy}
                  onClick={() => void applySlaveMode()}
                >
                  Применить Slave
                </Button>
              </div>
            </div>
          )}

          {modeDraft === 'wg' && (
            <div className="space-y-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div className="min-w-0 flex-1 space-y-2">
                  <Label htmlFor="wg-config">Файл WireGuard</Label>
                  {wgConfigs.length > 0 ? (
                    <Select value={wgConfigPath} onValueChange={setWgConfigPath} disabled={disabled || busy}>
                      <SelectTrigger id="wg-config" className="w-full lg:max-w-lg font-mono text-sm">
                        <SelectValue placeholder="Выберите .conf" />
                      </SelectTrigger>
                      <SelectContent>
                        {wgConfigs.map((path) => (
                          <SelectItem key={path} value={path} className="font-mono text-xs">
                            {path}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      id="wg-config"
                      className="font-mono text-sm"
                      placeholder="/root/vpn.conf"
                      value={wgConfigPath}
                      disabled={disabled || busy}
                      onChange={(e) => setWgConfigPath(e.target.value)}
                    />
                  )}
                  <p className="text-xs text-muted-foreground">Конфиги из /root/ и /root/warper/</p>
                </div>
                <Button
                  className="w-full shrink-0 lg:w-auto"
                  disabled={disabled || busy}
                  onClick={() => void applyWgMode()}
                >
                  Применить WireGuard
                </Button>
              </div>
            </div>
          )}
        </div>
      </WarperSection>

      <div className="grid gap-4 lg:grid-cols-2">
        <WarperSection title="Сеть WARP" icon={Network} description="FullVPN и подсеть маршрутизации">
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-3 rounded-lg border p-3">
              <div>
                <div className="text-sm font-medium">FullVPN</div>
                <p className="text-xs text-muted-foreground">Весь VPN-трафик через AZ-WARP</p>
              </div>
              <Switch
                checked={fullVpn}
                disabled={disabled || busy}
                onCheckedChange={(checked) => void saveFullVpn(checked)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="warp-subnet">Подсеть WARP</Label>
              <div className="flex gap-2">
                <Input
                  id="warp-subnet"
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
        </WarperSection>

        <WarperSection title="Параметры sing-box" icon={Gauge} description="MTU и уровень логирования">
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="warper-mtu">MTU</Label>
              <div className="flex gap-2">
                <Input
                  id="warper-mtu"
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
            </div>
            <div className="space-y-2">
              <Label>Уровень логов</Label>
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
        </WarperSection>
      </div>

      <WarperSection
        title="Управление sing-box"
        icon={RotateCw}
        description="Запуск, остановка и перезапуск службы"
      >
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" disabled={disabled || busy} onClick={() => void runSingbox('start')}>
            <Play className="mr-1.5 h-4 w-4" />
            Старт
          </Button>
          <Button size="sm" variant="secondary" disabled={disabled || busy} onClick={() => void runSingbox('stop')}>
            <Square className="mr-1.5 h-4 w-4" />
            Стоп
          </Button>
          <Button size="sm" disabled={disabled || busy} onClick={() => void runSingbox('restart')}>
            <RefreshCw className="mr-1.5 h-4 w-4" />
            Перезапуск
          </Button>
        </div>
      </WarperSection>
    </div>
  )
}
