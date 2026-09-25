import { useCallback, useEffect, useState } from 'react'
import {
  Cloud,
  FileKey,
  Gauge,
  Network,
  Play,
  RefreshCw,
  Server,
  Settings2,
  Shield,
  ShieldCheck,
  Square,
  RotateCw,
  Wrench,
  Zap,
  ArrowUpCircle,
} from 'lucide-react'
import {
  forgetWarperOvpnCredentials,
  getWarperMode,
  getWarperSettingsOptions,
  getWarperSingboxStatus,
  getWarperSubnets,
  postWarperResync,
  postWarperSingbox,
  setWarperAutopatch,
  setWarperFullVpn,
  setWarperLogLevel,
  setWarperModeHy2,
  setWarperModeOpenVpn,
  setWarperModeSlave,
  setWarperModeSlaveLink,
  setWarperModeVless,
  setWarperModeWarp,
  setWarperModeWg,
  setWarperMtu,
  setWarperSubnet,
} from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
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
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import type {
  WarperHealthResponse,
  WarperOvpnConfig,
  WarperSingboxStatusResponse,
  WarperWarpKeyItem,
} from '@/types'
import { cn } from '@/lib/utils'
import WarperSection, { WarperStatTile } from './WarperSection'
import WarperUpdatesSection from './WarperUpdatesSection'
import {
  DEFAULT_FAKE_SUBNET,
  formatOutboundMode,
  isWarperDisabled,
  normalizeOutboundMode,
  OUTBOUND_MODE_OPTIONS,
  WARP_KEY_SOURCES,
  type WarperOutboundMode,
  type WarperWarpKeySource,
} from './utils'

const LOG_LEVELS = ['debug', 'info', 'warn', 'error'] as const

const SUBNET_LABELS: Record<string, string> = {
  antizapret: 'Клиенты AntiZapret',
  fullvpn: 'Клиенты full VPN',
  all: 'Все клиенты',
  route_mode: 'Режим IP-маршрутов',
  route_source: 'Источник маршрутов',
}

function fileBasename(path: string): string {
  const parts = path.split('/').filter(Boolean)
  return parts[parts.length - 1] ?? path
}

function keySourceLabel(source: string): string {
  return WARP_KEY_SOURCES.find((item) => item.value === source)?.label ?? source
}

function readOutbound(mode: Record<string, unknown>): Record<string, unknown> | null {
  const raw = mode.outbound
  return raw && typeof raw === 'object' && !Array.isArray(raw) ? (raw as Record<string, unknown>) : null
}

const MTU_MIN = 1280
const MTU_MAX = 1500
const CIDR_RE = /^(\d{1,3})(\.\d{1,3}){3}\/\d{1,2}$/

function linkError(value: string, schemes: string[]): string | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const lower = trimmed.toLowerCase()
  return schemes.some((scheme) => lower.startsWith(`${scheme}://`))
    ? null
    : `Ссылка должна начинаться с ${schemes.map((scheme) => `${scheme}://`).join(' или ')}`
}

function isValidPort(value: string): boolean {
  const port = Number(value)
  return Number.isInteger(port) && port >= 1 && port <= 65535
}

function singboxStateLabel(status: WarperSingboxStatusResponse): string {
  if (status.active) return 'Работает'
  const state = (status.state ?? '').toLowerCase()
  if (state === 'failed') return 'Ошибка'
  if (state === 'activating') return 'Запускается'
  if (state === 'deactivating') return 'Останавливается'
  return 'Остановлен'
}

function FieldError({ message }: { message: string | null }) {
  if (!message) return null
  return <p className="text-xs text-destructive">{message}</p>
}

interface SettingsTabProps {
  health: WarperHealthResponse | null
}

export default function SettingsTab({ health }: SettingsTabProps) {
  const { activeNode } = useNode()
  const { success, error: notifyError } = useNotifications()
  const { confirm, dialogProps } = useConfirmDialog()
  const disabled = isWarperDisabled(health)

  const [mode, setMode] = useState<Record<string, unknown>>({})
  const [warpKeys, setWarpKeys] = useState<WarperWarpKeyItem[]>([])
  const [wgConfigs, setWgConfigs] = useState<string[]>([])
  const [ovpnConfigs, setOvpnConfigs] = useState<WarperOvpnConfig[]>([])
  const [singbox, setSingbox] = useState<WarperSingboxStatusResponse | null>(null)
  const [subnets, setSubnets] = useState<Record<string, string>>({})
  const [mtu, setMtu] = useState('1420')
  const [logLevel, setLogLevel] = useState<string>('info')
  const [subnet, setSubnet] = useState('')
  const [fullVpn, setFullVpn] = useState(false)
  const [autopatch, setAutopatch] = useState<boolean | null>(null)
  const [warpKeySource, setWarpKeySource] = useState<WarperWarpKeySource>('auto')
  const [modeDraft, setModeDraft] = useState<WarperOutboundMode>('warp')
  const [slaveLink, setSlaveLink] = useState('')
  const [slaveManual, setSlaveManual] = useState(false)
  const [slaveHost, setSlaveHost] = useState('')
  const [slavePort, setSlavePort] = useState('8444')
  const [slaveKey, setSlaveKey] = useState('')
  const [wgConfigPath, setWgConfigPath] = useState('')
  const [vlessLink, setVlessLink] = useState('')
  const [hy2Link, setHy2Link] = useState('')
  const [ovpnPath, setOvpnPath] = useState('')
  const [ovpnUser, setOvpnUser] = useState('')
  const [ovpnPassword, setOvpnPassword] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const currentMode = normalizeOutboundMode(mode.outbound_mode ?? mode.mode)
  const outboundLabel = typeof mode.outbound_label === 'string' ? mode.outbound_label : null
  const outbound = readOutbound(mode)
  const selectedOvpn = ovpnConfigs.find((item) => item.path === ovpnPath) ?? null

  const savedMtu = typeof mode.mtu === 'number' ? String(mode.mtu) : null
  const savedLogLevel = typeof mode.log_level === 'string' ? mode.log_level : null
  const savedSubnet = typeof mode.subnet === 'string' ? mode.subnet : ''
  const mtuNumber = Number(mtu)
  const mtuError =
    mtu.trim() && (!Number.isInteger(mtuNumber) || mtuNumber < MTU_MIN || mtuNumber > MTU_MAX)
      ? `MTU должен быть целым числом от ${MTU_MIN} до ${MTU_MAX}`
      : null
  const subnetError = subnet.trim() && !CIDR_RE.test(subnet.trim()) ? `Укажите подсеть в формате ${DEFAULT_FAKE_SUBNET}` : null
  const slaveLinkError = linkError(slaveLink, ['ss'])
  const slavePortError = slavePort.trim() && !isValidPort(slavePort) ? 'Порт 1–65535' : null
  const vlessError = linkError(vlessLink, ['vless'])
  const hy2Error = linkError(hy2Link, ['hy2', 'hysteria2'])
  const ovpnPasswordMissing = Boolean(ovpnUser.trim()) && !ovpnPassword

  const slaveReady = slaveManual
    ? Boolean(slaveHost.trim() && slaveKey.trim()) && isValidPort(slavePort)
    : Boolean(slaveLink.trim()) && !slaveLinkError
  const wgReady = Boolean(wgConfigPath.trim())
  const vlessReady = Boolean(vlessLink.trim()) && !vlessError
  const hy2Ready = Boolean(hy2Link.trim()) && !hy2Error
  const ovpnReady = Boolean(ovpnPath.trim()) && !ovpnPasswordMissing
  const mtuDirty = Boolean(mtu.trim()) && mtu !== savedMtu
  const logLevelDirty = logLevel !== savedLogLevel
  const subnetDirty = Boolean(subnet.trim()) && subnet.trim() !== savedSubnet

  const loadExtras = useCallback(async () => {
    const [singboxResult, subnetsResult] = await Promise.allSettled([getWarperSingboxStatus(), getWarperSubnets()])
    setSingbox(singboxResult.status === 'fulfilled' ? singboxResult.value : null)
    setSubnets(subnetsResult.status === 'fulfilled' ? subnetsResult.value.subnets ?? {} : {})
  }, [])

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
      const keyItems =
        optionsResponse.warp_key_items && optionsResponse.warp_key_items.length > 0
          ? optionsResponse.warp_key_items
          : (optionsResponse.warp_keys ?? []).map((path) => ({ source: '', path, address: '', is_current: false }))
      setWarpKeys(keyItems)
      const configs = optionsResponse.wg_configs ?? []
      setWgConfigs(configs)
      const ovpn = optionsResponse.ovpn_configs ?? []
      setOvpnConfigs(ovpn)
      if (typeof modeData.mtu === 'number') setMtu(String(modeData.mtu))
      if (typeof modeData.log_level === 'string') setLogLevel(modeData.log_level)
      if (typeof modeData.subnet === 'string') setSubnet(modeData.subnet)
      if (typeof modeData.fullvpn === 'boolean') setFullVpn(modeData.fullvpn)
      setAutopatch(typeof modeData.autopatch === 'boolean' ? modeData.autopatch : null)
      const active = normalizeOutboundMode(modeData.outbound_mode ?? modeData.mode)
      if (active) setModeDraft(active)
      if (configs.length > 0) {
        setWgConfigPath((current) => (current && configs.includes(current) ? current : configs[0]))
      }
      if (ovpn.length > 0) {
        setOvpnPath((current) => (current && ovpn.some((item) => item.path === current) ? current : ovpn[0].path))
      }
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось загрузить настройки')
    } finally {
      setLoading(false)
    }
    void loadExtras()
  }, [health?.installed, loadExtras, notifyError])

  useEffect(() => {
    void load()
  }, [load, activeNode?.id])

  async function runAction(action: () => Promise<{ message?: string | null }>, okMessage: string, failMessage: string) {
    setBusy(true)
    try {
      const result = await action()
      success(result.message || okMessage)
      await load()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : failMessage)
    } finally {
      setBusy(false)
    }
  }

  function runSingbox(action: 'start' | 'stop' | 'restart' | 'enable' | 'disable' | 'upgrade') {
    const messages = {
      start: 'sing-box запущен',
      stop: 'sing-box остановлен',
      restart: 'sing-box перезапущен',
      enable: 'Автозагрузка sing-box включена',
      disable: 'Автозагрузка sing-box выключена',
      upgrade: 'sing-box обновлён',
    } as const
    return runAction(() => postWarperSingbox(action), messages[action], 'Ошибка sing-box')
  }

  function confirmSingboxStop() {
    confirm({
      title: 'Остановить sing-box?',
      description:
        'Трафик через AZ-WARP перестанет ходить: домены и IP-подсети из списков AZ-WARP станут недоступны клиентам, пока sing-box не запустят снова.',
      confirmLabel: 'Остановить',
      destructive: true,
      onConfirm: () => runSingbox('stop'),
    })
  }

  function confirmSingboxUpgrade() {
    confirm({
      title: 'Обновить sing-box?',
      description:
        'Будет установлена версия из установщика AZ-WARP. Конфиг проверяется заранее, затем служба перезапускается — соединения клиентов через AZ-WARP кратковременно оборвутся.',
      confirmLabel: 'Обновить',
      onConfirm: () => runSingbox('upgrade'),
    })
  }

  function saveMtu() {
    if (mtuError || !mtuDirty) return
    return runAction(() => setWarperMtu(mtuNumber), `MTU установлен: ${mtuNumber}`, 'Не удалось сохранить MTU')
  }

  function saveLogLevel() {
    return runAction(() => setWarperLogLevel(logLevel), `Уровень логов: ${logLevel}`, 'Не удалось сохранить уровень логов')
  }

  function applyWarpMode() {
    const keySource = warpKeySource === 'auto' ? null : warpKeySource
    return runAction(() => setWarperModeWarp(keySource), 'Режим WARP применён', 'Не удалось переключить WARP')
  }

  function applySlaveMode() {
    if (!slaveManual) {
      if (!slaveLink.trim()) return
      return runAction(() => setWarperModeSlaveLink(slaveLink.trim()), 'Режим Slave применён', 'Не удалось переключить Slave')
    }
    const port = Number(slavePort)
    if (!slaveHost.trim() || !slaveKey.trim() || !Number.isFinite(port)) return
    return runAction(
      () => setWarperModeSlave(slaveHost.trim(), port, slaveKey.trim()),
      'Режим Slave применён',
      'Не удалось переключить Slave',
    )
  }

  function applyWgMode() {
    if (!wgConfigPath.trim()) return
    return runAction(() => setWarperModeWg(wgConfigPath.trim()), 'Режим WireGuard применён', 'Не удалось переключить WireGuard')
  }

  function applyVlessMode() {
    if (!vlessLink.trim()) return
    return runAction(() => setWarperModeVless(vlessLink.trim()), 'Режим VLESS применён', 'Не удалось переключить VLESS')
  }

  function applyHy2Mode() {
    if (!hy2Link.trim()) return
    return runAction(() => setWarperModeHy2(hy2Link.trim()), 'Режим Hysteria2 применён', 'Не удалось переключить Hysteria2')
  }

  async function applyOpenVpnMode() {
    if (!ovpnPath.trim()) return
    await runAction(
      () => setWarperModeOpenVpn(ovpnPath.trim(), ovpnUser.trim() || null, ovpnUser.trim() ? ovpnPassword : null),
      'Режим OpenVPN применён',
      'Не удалось переключить OpenVPN',
    )
    setOvpnPassword('')
  }

  function forgetOvpn() {
    if (!ovpnPath.trim()) return
    return runAction(() => forgetWarperOvpnCredentials(ovpnPath.trim()), 'Логин и пароль удалены', 'Не удалось удалить логин')
  }

  async function saveFullVpn(enable: boolean) {
    setFullVpn(enable)
    await runAction(() => setWarperFullVpn(enable), `FullVPN ${enable ? 'включён' : 'выключен'}`, 'Не удалось изменить FullVPN')
  }

  async function saveAutopatch(enable: boolean) {
    setAutopatch(enable)
    await runAction(
      () => setWarperAutopatch(enable),
      `Автопатч DNS ${enable ? 'включён' : 'выключен'}`,
      'Не удалось изменить автопатч',
    )
  }

  function saveSubnet() {
    const value = subnet.trim()
    if (!value || subnetError || !subnetDirty) return
    confirm({
      title: `Сменить fake-подсеть на ${value}?`,
      description:
        'Правила AZ-WARP и DNS-патч будут переприменены. Клиентам AntiZapret нужно переподключиться, иначе домены AZ-WARP у них перестанут открываться.',
      confirmLabel: 'Сменить подсеть',
      destructive: true,
      onConfirm: () => runAction(() => setWarperSubnet(value), 'Подсеть обновлена', 'Не удалось сохранить подсеть'),
    })
  }

  function runResync() {
    return runAction(() => postWarperResync(), 'Состояние AZ-WARP восстановлено', 'Не удалось выполнить resync')
  }

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner label="Загрузка настроек AZ-WARP..." />
      </div>
    )
  }

  const modeIcons = { warp: Cloud, slave: Server, wg: Shield, vless: Zap, hy2: Zap, openvpn: FileKey } as const
  const controlsDisabled = disabled || busy

  return (
    <div className="space-y-4">
      <ConfirmDialogHost dialogProps={dialogProps} />
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
          value={formatOutboundMode(currentMode ?? (typeof mode.outbound_mode === 'string' ? mode.outbound_mode : null))}
          hint={outboundLabel ?? 'Активная конфигурация выхода'}
        />
        <WarperStatTile label="MTU sing-box" value={mtu} hint="1280–1500" />
        <WarperStatTile
          label="sing-box"
          value={singbox ? singboxStateLabel(singbox) : '—'}
          hint={singbox?.version ? `Версия ${singbox.version}` : `Логи: ${logLevel}`}
        />
        <WarperStatTile label="FullVPN" value={fullVpn ? 'Включён' : 'Выключен'} />
      </div>

      <WarperSection
        title="Режим выхода"
        icon={Cloud}
        description="Выберите способ маршрутизации трафика и настройте параметры. Смена режима атомарная: при ошибке остаются прежние режим и конфиг."
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {OUTBOUND_MODE_OPTIONS.map((option) => {
            const Icon = modeIcons[option.id]
            const selected = modeDraft === option.id
            const active = currentMode === option.id
            return (
              <button
                key={option.id}
                type="button"
                disabled={controlsDisabled}
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

        {outbound && currentMode && ['vless', 'hy2', 'openvpn'].includes(currentMode) && (
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
            {Object.entries(outbound).map(([key, value]) => (
              <span key={key} className="rounded border bg-muted/30 px-2 py-0.5 font-mono">
                {key}: {Array.isArray(value) ? value.join(',') : String(value)}
              </span>
            ))}
          </div>
        )}

        <div className="mt-4 rounded-lg border bg-muted/10 p-4">
          {modeDraft === 'warp' && (
            <div className="space-y-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div className="min-w-0 flex-1 space-y-2">
                  <Label htmlFor="warp-key-source">Источник WARP-ключа</Label>
                  <Select
                    value={warpKeySource}
                    onValueChange={(value) => setWarpKeySource(value as WarperWarpKeySource)}
                    disabled={controlsDisabled}
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
                <Button className="w-full shrink-0 lg:w-auto" disabled={controlsDisabled} onClick={() => void applyWarpMode()}>
                  Применить WARP
                </Button>
              </div>

              {warpKeys.length > 0 && (
                <div className="rounded-md border bg-background/40 px-3 py-2.5">
                  <p className="mb-2 text-xs font-medium text-muted-foreground">
                    Найденные ключи на узле ({warpKeys.length})
                  </p>
                  <ul className="grid gap-2 sm:grid-cols-2">
                    {warpKeys.map((key) => (
                      <li
                        key={key.path}
                        className={cn(
                          'flex min-w-0 items-start gap-2 rounded-md border bg-muted/20 px-2.5 py-2',
                          key.is_current && 'border-primary/50',
                        )}
                      >
                        <Cloud className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary/70" />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="truncate text-sm font-medium">
                              {key.source ? keySourceLabel(key.source) : fileBasename(key.path)}
                            </span>
                            {key.is_current && <Badge variant="success">Текущий</Badge>}
                          </div>
                          <div className="truncate font-mono text-[11px] text-muted-foreground" title={key.path}>
                            {key.path}
                          </div>
                          {key.address && (
                            <div className="truncate font-mono text-[11px] text-muted-foreground">{key.address}</div>
                          )}
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
              {!slaveManual ? (
                <div className="space-y-1.5">
                  <Label htmlFor="slave-link">Ссылка донора</Label>
                  <Input
                    id="slave-link"
                    className="font-mono text-sm"
                    placeholder="ss://…"
                    value={slaveLink}
                    disabled={controlsDisabled}
                    aria-invalid={Boolean(slaveLinkError)}
                    onChange={(e) => setSlaveLink(e.target.value)}
                  />
                  <FieldError message={slaveLinkError} />
                  <p className="text-xs text-muted-foreground">
                    Выполните <code>warperslave link</code> на доноре и вставьте ссылку ss://. Для доноров на VLESS
                    или Hysteria2 выберите соответствующий режим.
                  </p>
                </div>
              ) : (
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="slave-host">Host</Label>
                    <Input
                      id="slave-host"
                      placeholder="1.2.3.4"
                      value={slaveHost}
                      disabled={controlsDisabled}
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
                      disabled={controlsDisabled}
                      aria-invalid={Boolean(slavePortError)}
                      onChange={(e) => setSlavePort(e.target.value)}
                    />
                    <FieldError message={slavePortError} />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="slave-key">SS-key</Label>
                    <Input
                      id="slave-key"
                      placeholder="ss-key"
                      value={slaveKey}
                      disabled={controlsDisabled}
                      onChange={(e) => setSlaveKey(e.target.value)}
                    />
                  </div>
                </div>
              )}
              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
                <Button variant="link" size="sm" className="px-0" onClick={() => setSlaveManual((value) => !value)}>
                  {slaveManual ? 'Вставить ссылку ss://' : 'Ввести host, port и ключ вручную'}
                </Button>
                <Button
                  className="w-full sm:w-auto"
                  disabled={controlsDisabled || !slaveReady}
                  onClick={() => void applySlaveMode()}
                >
                  Применить Slave
                </Button>
              </div>
            </div>
          )}

          {modeDraft === 'wg' && (
            <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
              <div className="min-w-0 flex-1 space-y-2">
                <Label htmlFor="wg-config">Файл WireGuard</Label>
                {wgConfigs.length > 0 ? (
                  <Select value={wgConfigPath} onValueChange={setWgConfigPath} disabled={controlsDisabled}>
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
                    disabled={controlsDisabled}
                    onChange={(e) => setWgConfigPath(e.target.value)}
                  />
                )}
                <p className="text-xs text-muted-foreground">
                  Конфиги из /root/ и /root/warper/. PresharedKey необязателен, MTU и DNS берутся из файла.
                </p>
              </div>
              <Button
                className="w-full shrink-0 lg:w-auto"
                disabled={controlsDisabled || !wgReady}
                onClick={() => void applyWgMode()}
              >
                Применить WireGuard
              </Button>
            </div>
          )}

          {modeDraft === 'vless' && (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="vless-link">Ссылка vless://</Label>
                <Input
                  id="vless-link"
                  className="font-mono text-sm"
                  placeholder="vless://uuid@host:443?security=reality&…"
                  value={vlessLink}
                  disabled={controlsDisabled}
                  aria-invalid={Boolean(vlessError)}
                  onChange={(e) => setVlessLink(e.target.value)}
                />
                <FieldError message={vlessError} />
                <p className="text-xs text-muted-foreground">
                  Reality, транспорты ws / grpc / httpupgrade / http, flow xtls-rprx-vision. VLESS Encryption
                  (mlkem768x25519plus) в sing-box не поддерживается. Свой донор выдаёт ссылку командой{' '}
                  <code>warperslave link</code>.
                </p>
              </div>
              <div className="flex justify-end">
                <Button
                  className="w-full sm:w-auto"
                  disabled={controlsDisabled || !vlessReady}
                  onClick={() => void applyVlessMode()}
                >
                  Применить VLESS
                </Button>
              </div>
            </div>
          )}

          {modeDraft === 'hy2' && (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="hy2-link">Ссылка hy2://</Label>
                <Input
                  id="hy2-link"
                  className="font-mono text-sm"
                  placeholder="hy2://password@host:443?sni=…"
                  value={hy2Link}
                  disabled={controlsDisabled}
                  aria-invalid={Boolean(hy2Error)}
                  onChange={(e) => setHy2Link(e.target.value)}
                />
                <FieldError message={hy2Error} />
                <p className="text-xs text-muted-foreground">
                  Поддерживаются obfs salamander, диапазоны портов и пиннинг сертификата (pinSHA256).
                </p>
              </div>
              <div className="flex justify-end">
                <Button
                  className="w-full sm:w-auto"
                  disabled={controlsDisabled || !hy2Ready}
                  onClick={() => void applyHy2Mode()}
                >
                  Применить Hysteria2
                </Button>
              </div>
            </div>
          )}

          {modeDraft === 'openvpn' && (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="ovpn-config">Файл .ovpn</Label>
                {ovpnConfigs.length > 0 ? (
                  <Select value={ovpnPath} onValueChange={setOvpnPath} disabled={controlsDisabled}>
                    <SelectTrigger id="ovpn-config" className="w-full lg:max-w-lg font-mono text-sm">
                      <SelectValue placeholder="Выберите .ovpn" />
                    </SelectTrigger>
                    <SelectContent>
                      {ovpnConfigs.map((item) => (
                        <SelectItem key={item.path} value={item.path} className="font-mono text-xs">
                          {item.path}
                          {item.server ? ` → ${item.server}` : ''}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input
                    id="ovpn-config"
                    className="font-mono text-sm"
                    placeholder="/root/provider.ovpn"
                    value={ovpnPath}
                    disabled={controlsDisabled}
                    onChange={(e) => setOvpnPath(e.target.value)}
                  />
                )}
                <p className="text-xs text-muted-foreground">
                  Файлы из /root/ и /root/warper/. dev tap и статический ключ sing-box не поддерживает.
                </p>
              </div>

              {(selectedOvpn?.needs_auth ?? !selectedOvpn) && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="ovpn-user">Логин</Label>
                    <Input
                      id="ovpn-user"
                      autoComplete="off"
                      placeholder={selectedOvpn?.saved_user ? `Сохранён: ${selectedOvpn.saved_user}` : 'если требуется'}
                      value={ovpnUser}
                      disabled={controlsDisabled}
                      onChange={(e) => setOvpnUser(e.target.value)}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="ovpn-password">Пароль</Label>
                    <Input
                      id="ovpn-password"
                      type="password"
                      autoComplete="new-password"
                      value={ovpnPassword}
                      disabled={controlsDisabled || !ovpnUser.trim()}
                      aria-invalid={ovpnPasswordMissing}
                      onChange={(e) => setOvpnPassword(e.target.value)}
                    />
                    <FieldError message={ovpnPasswordMissing ? 'Введите пароль для этого логина' : null} />
                  </div>
                  <p className="text-xs text-muted-foreground sm:col-span-2">
                    Логин и пароль запоминаются для каждого .ovpn отдельно. Оставьте поля пустыми, чтобы
                    использовать сохранённые.
                  </p>
                </div>
              )}

              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
                {selectedOvpn?.saved_user ? (
                  <Button variant="outline" size="sm" disabled={controlsDisabled} onClick={() => void forgetOvpn()}>
                    Забыть логин ({selectedOvpn.saved_user})
                  </Button>
                ) : (
                  <span />
                )}
                <Button
                  className="w-full sm:w-auto"
                  disabled={controlsDisabled || !ovpnReady}
                  onClick={() => void applyOpenVpnMode()}
                >
                  Применить OpenVPN
                </Button>
              </div>
            </div>
          )}
        </div>
      </WarperSection>

      <div className="grid gap-4 lg:grid-cols-2">
        <WarperSection title="Сеть WARP" icon={Network} description="FullVPN, автопатч DNS и fake-подсеть">
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-3 rounded-lg border p-3">
              <div>
                <div className="text-sm font-medium">FullVPN</div>
                <p className="text-xs text-muted-foreground">WARP-резолвинг доменов и для клиентов full VPN</p>
              </div>
              <Switch
                checked={fullVpn}
                disabled={controlsDisabled}
                onCheckedChange={(checked) => void saveFullVpn(checked)}
              />
            </div>
            <div className="flex items-center justify-between gap-3 rounded-lg border p-3">
              <div>
                <div className="text-sm font-medium">Автопатч DNS при загрузке</div>
                <p className="text-xs text-muted-foreground">Служба warper-autopatch переприменяет патч kresd</p>
              </div>
              <Switch
                checked={Boolean(autopatch)}
                disabled={controlsDisabled || autopatch === null}
                onCheckedChange={(checked) => void saveAutopatch(checked)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="warp-subnet">Fake-подсеть</Label>
              <div className="flex gap-2">
                <Input
                  id="warp-subnet"
                  placeholder={DEFAULT_FAKE_SUBNET}
                  value={subnet}
                  disabled={controlsDisabled}
                  aria-invalid={Boolean(subnetError)}
                  onChange={(e) => setSubnet(e.target.value)}
                />
                <Button disabled={controlsDisabled || !subnetDirty || Boolean(subnetError)} onClick={saveSubnet}>
                  Сохранить
                </Button>
              </div>
              <FieldError message={subnetError} />
              <p className="text-xs text-muted-foreground">
                По умолчанию {DEFAULT_FAKE_SUBNET}. Не используйте 198.18.0.0/15 (занят AntiZapret) и 172.16.0.0/12
                (пул Docker). После смены подсети клиентам нужно переподключиться.
              </p>
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
                  min={MTU_MIN}
                  max={MTU_MAX}
                  value={mtu}
                  disabled={controlsDisabled}
                  aria-invalid={Boolean(mtuError)}
                  onChange={(e) => setMtu(e.target.value)}
                />
                <Button disabled={controlsDisabled || !mtuDirty || Boolean(mtuError)} onClick={() => void saveMtu()}>
                  Сохранить
                </Button>
              </div>
              {mtuError ? (
                <FieldError message={mtuError} />
              ) : (
                <p className="text-xs text-muted-foreground">
                  {MTU_MIN}–{MTU_MAX}, по умолчанию 1420. Снижайте при обрывах на мобильных сетях.
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label>Уровень логов</Label>
              <div className="flex gap-2">
                <Select value={logLevel} onValueChange={setLogLevel} disabled={controlsDisabled}>
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
                <Button disabled={controlsDisabled || !logLevelDirty} onClick={() => void saveLogLevel()}>
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
        description="Запуск, остановка, автозагрузка и обновление бинарника sing-box"
      >
        <div className="space-y-4">
          {singbox && (
            <div className="flex flex-col gap-3 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span
                  className={cn(
                    'h-2.5 w-2.5 rounded-full',
                    singbox.active ? 'bg-emerald-500' : singbox.state === 'failed' ? 'bg-destructive' : 'bg-muted-foreground/50',
                  )}
                  aria-hidden
                />
                <span className="font-medium">{singboxStateLabel(singbox)}</span>
                {singbox.version && <Badge variant="outline">sing-box {singbox.version}</Badge>}
                {!singbox.active && singbox.state !== 'failed' && (
                  <span className="text-xs text-muted-foreground">трафик через AZ-WARP не идёт</span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Запуск при загрузке узла</span>
                <Switch
                  checked={singbox.enabled}
                  disabled={controlsDisabled}
                  aria-label="Запуск sing-box при загрузке узла"
                  onCheckedChange={(checked) => void runSingbox(checked ? 'enable' : 'disable')}
                />
              </div>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {!singbox?.active && (
              <Button size="sm" disabled={controlsDisabled} onClick={() => void runSingbox('start')}>
                <Play className="mr-1.5 h-4 w-4" />
                Запустить
              </Button>
            )}
            {(!singbox || singbox.active) && (
              <>
                <Button
                  size="sm"
                  variant={singbox ? 'default' : 'secondary'}
                  disabled={controlsDisabled}
                  onClick={() => void runSingbox('restart')}
                >
                  <RefreshCw className="mr-1.5 h-4 w-4" />
                  Перезапустить
                </Button>
                <Button size="sm" variant="outline" disabled={controlsDisabled} onClick={confirmSingboxStop}>
                  <Square className="mr-1.5 h-4 w-4" />
                  Остановить
                </Button>
              </>
            )}
            {singbox && (
              <Button size="sm" variant="outline" disabled={controlsDisabled} onClick={confirmSingboxUpgrade}>
                <ArrowUpCircle className="mr-1.5 h-4 w-4" />
                Обновить sing-box
              </Button>
            )}
          </div>
        </div>
      </WarperSection>

      <WarperSection
        title="Обслуживание"
        icon={Wrench}
        description="Восстановление правил после пересборки AntiZapret и подсети клиентов"
      >
        <div className="space-y-4">
          <div className="flex flex-col gap-3 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-center gap-2 text-sm font-medium">
                <ShieldCheck className="h-4 w-4 text-primary" />
                Восстановить (resync)
              </div>
              <p className="text-xs text-muted-foreground">
                Переприменяет правила FORWARD, ipset, маршруты и патч kresd. Узел делает это сам раз в 10 минут
                и после ночной пересборки AntiZapret.
              </p>
            </div>
            <Button size="sm" variant="secondary" disabled={controlsDisabled} onClick={() => void runResync()}>
              Запустить resync
            </Button>
          </div>

          {Object.keys(subnets).length > 0 && (
            <dl className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
              {Object.entries(subnets).map(([key, value]) => (
                <div key={key} className="rounded-md border bg-muted/20 px-3 py-2">
                  <dt className="text-xs text-muted-foreground">{SUBNET_LABELS[key] ?? key}</dt>
                  <dd className="mt-0.5 font-mono text-xs">{value || '—'}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      </WarperSection>

      <WarperUpdatesSection health={health} />
    </div>
  )
}
