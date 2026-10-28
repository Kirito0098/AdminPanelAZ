import { useEffect, useMemo, useState } from 'react'
import { ArrowRight, ChevronLeft, Users as UsersIcon } from 'lucide-react'
import { getAssignableConfigs } from '@/api/configs'
import { getNodeSyncGroups, getNodes } from '@/api/nodes'
import { listPresets } from '@/api/users'
import { Node, PresetResponse } from '@/types'
import AppDialog from '@/components/shared/AppDialog'
import { Button } from '@/components/ui/button'
import { CardDescription, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { formatDate } from '@/lib/datetime'
import { cn } from '@/lib/utils'

type Step = 'who' | 'access' | 'summary'
type CreateMode = 'provision' | 'from_existing'

type ConfigOption = {
  id: number
  name: string
  vpn_type: string
  node_name: string
  description?: string | null
  owner_id: number | null
  owner_username?: string | null
  owner_is_admin: boolean
}

const VPN_TYPE_LABEL: Record<string, string> = {
  wireguard: 'WireGuard',
  openvpn: 'OpenVPN',
  amneziawg2: 'AmneziaWG 2.0',
}

function vpnTypeLabel(vpnType: string): string {
  return VPN_TYPE_LABEL[vpnType] ?? vpnType
}

function configOptionSubtitle(cfg: ConfigOption): string {
  const parts: string[] = [cfg.node_name, vpnTypeLabel(cfg.vpn_type)]
  if (cfg.description?.trim()) parts.push(cfg.description.trim())
  if (cfg.owner_username) parts.push(`владелец: ${cfg.owner_username}`)
  else if (cfg.owner_id == null) parts.push('без владельца')
  else parts.push(`owner_id: ${cfg.owner_id}`)
  parts.push(`#${cfg.id}`)
  return parts.join(' · ')
}

export type CreateUserPayload = {
  mode: CreateMode
  username: string
  client_base_name?: string
  node_ids?: number[]
  protocols?: string[]
  config_count?: number
  config_ids?: number[]
  config_quota?: number | null
  access_until?: string | null
  panel_login_enabled: boolean
  password?: string | null
  telegram_id?: string | null
  preset_id?: number | null
}

interface CreateUserDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Current admin user id — filters configs to unowned ∪ this owner by default. */
  adminUserId?: number
  onCreate: (data: CreateUserPayload) => void | Promise<void>
}

const PROTOCOLS: { id: string; label: string; featureKeys: string[] }[] = [
  { id: 'wireguard', label: 'WireGuard', featureKeys: ['wireguard', 'amneziawg'] },
  { id: 'openvpn', label: 'OpenVPN', featureKeys: ['openvpn'] },
  { id: 'amneziawg2', label: 'AmneziaWG 2.0', featureKeys: ['awg2'] },
]

function protocolEnabled(
  isEnabled: (key: string) => boolean,
  featureKeys: string[],
): boolean {
  return featureKeys.some((key) => isEnabled(key))
}

function nodesMissingAwg2(nodes: Node[], selectedIds: number[]): Node[] {
  return nodes.filter((n) => selectedIds.includes(n.id) && n.awg2_installed !== true)
}

export default function CreateUserDialog({
  open,
  onOpenChange,
  adminUserId,
  onCreate,
}: CreateUserDialogProps) {
  const { isEnabled } = useFeatureModules()
  const availableProtocols = useMemo(
    () => PROTOCOLS.filter((p) => protocolEnabled(isEnabled, p.featureKeys)),
    [isEnabled],
  )
  const [step, setStep] = useState<Step>('who')
  const [mode, setMode] = useState<CreateMode>('provision')
  const [nodes, setNodes] = useState<Node[]>([])
  const [replicaIds, setReplicaIds] = useState<Set<number>>(new Set())
  const [nodesLoading, setNodesLoading] = useState(false)
  const [presets, setPresets] = useState<PresetResponse[]>([])
  const [selectedPresetId, setSelectedPresetId] = useState<number | null>(null)

  const [username, setUsername] = useState('')
  const [clientBaseName, setClientBaseName] = useState('')
  const [telegramId, setTelegramId] = useState('')
  const [panelLogin, setPanelLogin] = useState(false)
  const [password, setPassword] = useState('')
  const [selectedNodeIds, setSelectedNodeIds] = useState<number[]>([])
  const [selectedProtocols, setSelectedProtocols] = useState<string[]>([])
  const [configCount, setConfigCount] = useState(1)
  const [configQuota, setConfigQuota] = useState('')
  const [accessUntil, setAccessUntil] = useState('')
  const [configIds, setConfigIds] = useState<number[]>([])
  const [configOptions, setConfigOptions] = useState<ConfigOption[]>([])
  const [configsLoading, setConfigsLoading] = useState(false)
  const [configsLoaded, setConfigsLoaded] = useState(false)
  const [showAllOwners, setShowAllOwners] = useState(false)
  const [configSearch, setConfigSearch] = useState('')

  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) {
      setStep('who')
      setMode('provision')
      setUsername('')
      setClientBaseName('')
      setTelegramId('')
      setPanelLogin(false)
      setPassword('')
      setSelectedNodeIds([])
      setSelectedProtocols([])
      setConfigCount(1)
      setConfigQuota('')
      setAccessUntil('')
      setSelectedPresetId(null)
      setConfigIds([])
      setConfigOptions([])
      setConfigsLoaded(false)
      setShowAllOwners(false)
      setConfigSearch('')
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    setSelectedProtocols((prev) => {
      const allowed = new Set(availableProtocols.map((p) => p.id))
      const kept = prev.filter((id) => allowed.has(id))
      if (kept.length > 0) return kept
      return availableProtocols[0] ? [availableProtocols[0].id] : []
    })
  }, [open, availableProtocols])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setNodesLoading(true)
      try {
        const [list, groups] = await Promise.all([getNodes(), getNodeSyncGroups().catch(() => [])])
        if (cancelled) return
        const replicas = new Set<number>()
        for (const group of groups) {
          for (const id of group.replica_node_ids ?? []) replicas.add(id)
        }
        const assignableIds = new Set(
          list
            .filter((node) => (node.node_kind ?? 'vpn') === 'vpn' && !replicas.has(node.id))
            .map((node) => node.id),
        )
        setNodes(list)
        setReplicaIds(replicas)
        setSelectedNodeIds((prev) => prev.filter((id) => assignableIds.has(id)))
      } catch {
        /* узлы необязательны для шага «Доступ» — без них покажем подсказку */
      } finally {
        if (!cancelled) setNodesLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    const loadPresets = async () => {
      try {
        const list = await listPresets()
        if (!cancelled) setPresets(list)
      } catch {
        /* пресеты опциональны — без них будет подсказка */
      }
    }
    void loadPresets()
    return () => {
      cancelled = true
    }
  }, [open])

  useEffect(() => {
    if (!open || step !== 'access' || mode !== 'from_existing' || configsLoaded) return
    let cancelled = false
    const load = async () => {
      setConfigsLoading(true)
      try {
        const list = await getAssignableConfigs()
        if (cancelled) return
        setConfigOptions(
          list.map((c) => ({
            id: c.id,
            name: c.client_name,
            vpn_type: c.vpn_type,
            node_name: c.node_name,
            description: c.description ?? null,
            owner_id: c.owner_id,
            owner_username: c.owner_username ?? null,
            owner_is_admin: c.owner_is_admin,
          })),
        )
        setConfigsLoaded(true)
      } catch {
        if (!cancelled) setConfigOptions([])
      } finally {
        if (!cancelled) setConfigsLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [open, step, mode, configsLoaded])

  /** Прокси и реплики HA выдавать нельзя (сервер проверит ещё раз). */
  const assignableNodes = useMemo(
    () => nodes.filter((node) => (node.node_kind ?? 'vpn') === 'vpn' && !replicaIds.has(node.id)),
    [nodes, replicaIds],
  )

  const awg2Blocked = useMemo(
    () => nodesMissingAwg2(assignableNodes, selectedNodeIds),
    [assignableNodes, selectedNodeIds],
  )

  const awg2Enabled = availableProtocols.some((p) => p.id === 'amneziawg2')

  const visibleConfigs = useMemo(() => {
    let list = configOptions
    if (!showAllOwners) {
      // «Висящие на админах» + свои + без владельца — типичный кейс разнесения
      list = list.filter(
        (c) =>
          c.owner_id == null ||
          c.owner_is_admin ||
          (adminUserId != null && c.owner_id === adminUserId),
      )
    }
    const q = configSearch.trim().toLowerCase()
    if (q) {
      list = list.filter((c) => {
        const hay = [
          c.name,
          c.node_name,
          c.owner_username ?? '',
          vpnTypeLabel(c.vpn_type),
          c.vpn_type,
          c.description ?? '',
          String(c.id),
        ]
          .join(' ')
          .toLowerCase()
        return hay.includes(q)
      })
    }
    return list
  }, [configOptions, showAllOwners, adminUserId, configSearch])

  const selectedConfigNames = useMemo(() => {
    const byId = new Map(configOptions.map((c) => [c.id, c]))
    return configIds.map((id) => {
      const c = byId.get(id)
      if (!c) return `#${id}`
      return `${c.name} · ${c.node_name} · ${vpnTypeLabel(c.vpn_type)}`
    })
  }, [configIds, configOptions])

  const changeSelectedNodes = (nextIds: number[]) => {
    setSelectedNodeIds(nextIds)
    if (nodesMissingAwg2(assignableNodes, nextIds).length > 0) {
      setSelectedProtocols((prev) => prev.filter((id) => id !== 'amneziawg2'))
    }
  }

  const planNames = useMemo(() => {
    const names: string[] = []
    for (let i = 1; i <= configCount; i++) {
      names.push(i === 1 ? clientBaseName : `${clientBaseName}-${i}`)
    }
    return names
  }, [configCount, clientBaseName])

  const totalFiles = planNames.length * selectedProtocols.length * selectedNodeIds.length

  const goNext = () => {
    if (step === 'who') setStep('access')
    else if (step === 'access') setStep('summary')
  }
  const goPrev = () => {
    if (step === 'access') setStep('who')
    else if (step === 'summary') setStep('access')
  }

  const canProceed = () => {
    if (step === 'who') {
      if (!username.trim()) return false
      if (mode === 'from_existing') {
        if (panelLogin && password.length < 4) return false
        return true
      }
      return Boolean(clientBaseName.trim())
    }
    if (step === 'access') {
      if (mode === 'from_existing') return true
      return selectedNodeIds.length > 0 && selectedProtocols.length > 0
    }
    return true
  }

  const parsedQuota =
    configQuota.trim() === '' ? null : Number.parseInt(configQuota, 10) || undefined
  const parsedAccessUntil = accessUntil.trim() === '' ? undefined : accessUntil

  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      if (mode === 'from_existing') {
        await onCreate({
          mode: 'from_existing',
          username: username.trim(),
          config_ids: configIds,
          config_quota: parsedQuota,
          access_until: parsedAccessUntil,
          panel_login_enabled: panelLogin,
          password: panelLogin ? password : undefined,
          telegram_id: telegramId.trim() === '' ? undefined : telegramId.trim(),
        })
      } else {
        await onCreate({
          mode: 'provision',
          username: username.trim(),
          client_base_name: clientBaseName.trim(),
          node_ids: selectedNodeIds,
          protocols: selectedProtocols,
          config_count: configCount,
          config_quota: parsedQuota,
          access_until: parsedAccessUntil,
          panel_login_enabled: panelLogin,
          password: panelLogin ? password : undefined,
          telegram_id: telegramId.trim() === '' ? undefined : telegramId.trim(),
          preset_id: selectedPresetId,
        })
      }
    } finally {
      setSubmitting(false)
    }
  }

  const header = (title: string, description: string) => (
    <>
      <CardTitle className="flex items-center gap-2 text-base">{title}</CardTitle>
      <CardDescription className="mt-1">{description}</CardDescription>
    </>
  )

  const toggleConfigId = (id: number, next: boolean | 'indeterminate') => {
    setConfigIds((prev) => {
      const set = new Set(prev)
      if (next) set.add(id)
      else set.delete(id)
      return Array.from(set).sort((a, b) => a - b)
    })
  }

  return (
    <AppDialog
      open={open}
      onOpenChange={onOpenChange}
      title={step === 'summary' ? 'Сводка создания' : step === 'access' ? 'Доступ' : 'Кто'}
      description={
        step === 'summary'
          ? mode === 'from_existing'
            ? 'Проверьте логин и привязку конфигов'
            : 'Проверьте план перед созданием абонента'
          : undefined
      }
      icon={UsersIcon}
      size="lg"
      hideClose={step === 'summary'}
      footer={
        <>
          {step !== 'who' && (
            <Button type="button" variant="outline" onClick={goPrev} disabled={submitting}>
              <ChevronLeft size={16} />
              Назад
            </Button>
          )}
          {step === 'summary' ? (
            <Button type="button" onClick={handleSubmit} disabled={submitting}>
              {submitting ? 'Создание…' : <><ArrowRight size={16} /> Создать абонента</>}
            </Button>
          ) : (
            <>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Отмена
              </Button>
              <Button
                type="button"
                onClick={goNext}
                disabled={submitting || !canProceed()}
              >
                <><ArrowRight size={16} /> Далее</>
              </Button>
            </>
          )}
        </>
      }
    >
      <div className="space-y-4">
        {step === 'who' && (
          <>
            {header(
              'Кто войдёт',
              mode === 'from_existing'
                ? 'Логин абонента. Существующие конфиги привяжете на следующем шаге.'
                : 'Логин абонента и базовое имя конфигов. Имена конфигов будут client, client-2, …',
            )}
            <div className="flex items-center justify-between gap-3 rounded-xl border bg-muted/20 p-3">
              <div className="space-y-0.5">
                <Label htmlFor="createFromExisting">Без новых конфигов (привязать существующие)</Label>
                <p className="text-xs text-muted-foreground">
                  VPN на серверах не создаются — только смена владельца.
                </p>
              </div>
              <Switch
                id="createFromExisting"
                checked={mode === 'from_existing'}
                onCheckedChange={(on) => {
                  setMode(on ? 'from_existing' : 'provision')
                  setSelectedPresetId(null)
                  setConfigIds([])
                  if (!on) {
                    setConfigsLoaded(false)
                    setConfigOptions([])
                  }
                }}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="createUsername">Логин</Label>
              <Input
                id="createUsername"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="ivan"
                autoFocus
                className="h-9"
                required
              />
            </div>
            {mode === 'provision' && (
              <div className="space-y-1.5">
                <Label htmlFor="createBaseName">Базовое имя конфигов</Label>
                <Input
                  id="createBaseName"
                  value={clientBaseName}
                  onChange={(e) => setClientBaseName(e.target.value)}
                  placeholder="ivan"
                  className="h-9 font-mono"
                  required
                />
                <p className="text-xs text-muted-foreground">
                  Не заканчивайте на «-число» (например ivan-2) — такие имена зарезервированы под нумерацию
                </p>
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="createTelegramId">Telegram ID (необязательно)</Label>
              <Input
                id="createTelegramId"
                type="text"
                inputMode="numeric"
                value={telegramId}
                onChange={(e) => setTelegramId(e.target.value)}
                placeholder="123456789"
                className="h-9 font-mono"
              />
              <p className="text-xs text-muted-foreground">
                Оставьте пустым — привяжут позже через код в разделе Пользователи
              </p>
            </div>
            <div className="flex items-center justify-between gap-3 rounded-xl border bg-muted/20 p-3">
              <div className="space-y-0.5">
                <Label>Вход в панель</Label>
                <p className="text-xs text-muted-foreground">
                  Выкл. — абонент не сможет входить в админ-панель (только Telegram / конфиги)
                </p>
              </div>
              <Switch id="createPanelLogin" checked={panelLogin} onCheckedChange={setPanelLogin} />
            </div>
            {mode === 'provision' && presets.length > 0 && (
              <div className="space-y-1.5">
                <Label htmlFor="createPreset">Шаблон предоставления (необязательно)</Label>
                <select
                  id="createPreset"
                  value={String(selectedPresetId ?? '')}
                  onChange={(e) => {
                    const v = Number.parseInt(e.target.value, 10)
                    setSelectedPresetId(Number.isFinite(v) ? v : null)
                  }}
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                >
                  <option value="">Без шаблона</option>
                  {presets.map((p) => (
                    <option key={p.id} value={String(p.id)}>
                      {p.name} {p.is_default ? ' (по умолчанию)' : ''}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-muted-foreground">
                  Шаблон задаёт узлы, протоколы, число конфигов и срок доступа при одобрении заявки.
                </p>
              </div>
            )}
            {panelLogin && (
              <div className="space-y-1.5 rounded-xl border bg-muted/20 p-3">
                <Label htmlFor="createPassword">Пароль</Label>
                <Input
                  id="createPassword"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="h-9"
                  disabled={!panelLogin}
                />
                <p className="text-xs text-muted-foreground">Минимум 4 символа</p>
              </div>
            )}
          </>
        )}

        {step === 'access' && mode === 'from_existing' && (
          <>
            {header(
              'Доступ',
              'Привяжите существующие конфиги и при необходимости срок и квоту.',
            )}
            <p className="text-xs text-muted-foreground">
              VPN на серверах не создаются — только смена владельца.
            </p>

            <div className="space-y-1.5">
              <Label htmlFor="createAccessUntilExisting">Срок доступа (необязательно)</Label>
              <Input
                id="createAccessUntilExisting"
                type="date"
                value={accessUntil}
                onChange={(e) => setAccessUntil(e.target.value)}
                className="h-9"
              />
              <p className="text-xs text-muted-foreground">
                Пусто — бессрочно.
              </p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="createConfigQuotaExisting">Квота имён на пользователя (необязательно)</Label>
              <Input
                id="createConfigQuotaExisting"
                type="number"
                min={0}
                max={1000}
                value={configQuota}
                onChange={(e) => setConfigQuota(e.target.value)}
                placeholder="без лимита"
                className="h-9"
              />
              <p className="text-xs text-muted-foreground">
                Лимит имён конфигов на всех серверах. 0 — общий лимит панели
              </p>
            </div>

            <div className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Label>Конфиги</Label>
                <div className="flex items-center gap-2">
                  <Label htmlFor="createShowAllOwners" className="text-xs font-normal text-muted-foreground">
                    Показать все владельцы
                  </Label>
                  <Switch
                    id="createShowAllOwners"
                    checked={showAllOwners}
                    onCheckedChange={setShowAllOwners}
                  />
                </div>
              </div>
              <Input
                id="createConfigSearch"
                value={configSearch}
                onChange={(e) => setConfigSearch(e.target.value)}
                placeholder="Поиск: имя, узел, тип, владелец, #id…"
                className="h-9"
              />
              {configsLoading ? (
                <span className="text-xs text-muted-foreground">Загрузка конфигов…</span>
              ) : visibleConfigs.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  Нет подходящих конфигов. Можно создать абонента без привязки.
                </p>
              ) : (
                <div className="max-h-56 space-y-0.5 overflow-y-auto rounded-lg border p-1">
                  {visibleConfigs.map((cfg) => {
                    const checked = configIds.includes(cfg.id)
                    const subtitle = configOptionSubtitle(cfg)
                    return (
                      <label
                        key={cfg.id}
                        className={cn(
                          'flex items-center gap-2 rounded-md px-2.5 py-2 transition-colors',
                          checked
                            ? 'bg-primary/5'
                            : 'hover:bg-muted/50',
                        )}
                      >
                        <Checkbox
                          checked={checked}
                          onCheckedChange={(next) => toggleConfigId(cfg.id, next)}
                          aria-label={`${cfg.name} ${subtitle}`}
                        />
                        <div className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium font-mono">{cfg.name}</span>
                          <span className="block truncate text-[10px] text-muted-foreground">
                            {subtitle}
                          </span>
                        </div>
                      </label>
                    )
                  })}
                </div>
              )}
              {configIds.length > 0 && (
                <p className="text-xs text-muted-foreground">Выбрано: {configIds.length}</p>
              )}
            </div>
          </>
        )}

        {step === 'access' && mode === 'provision' && (
          <>
            {header(
              'Доступ',
              'Выберите узлы, протоколы и сколько имён конфигов создать на каждом узле.',
            )}
            <div className="space-y-1.5">
              <Label>Узлы</Label>
              {nodesLoading ? (
                <span className="text-xs text-muted-foreground">Загрузка узлов…</span>
              ) : assignableNodes.length === 0 ? (
                <p className="text-xs text-muted-foreground">Узлов нет — добавьте позже в карточке абонента</p>
              ) : (
                <div className="grid gap-1 sm:grid-cols-2">
                  {assignableNodes.map((node) => {
                    const checked = selectedNodeIds.includes(node.id)
                    return (
                      <label
                        key={node.id}
                        className={cn(
                          'flex items-center gap-2 rounded-lg border px-2.5 py-2 transition-colors',
                          checked
                            ? 'border-primary bg-primary/5'
                            : 'border-transparent hover:bg-muted/50',
                        )}
                      >
                        <Checkbox
                          checked={checked}
                          onCheckedChange={(next) => {
                            const ids = new Set(selectedNodeIds)
                            if (next) ids.add(node.id)
                            else ids.delete(node.id)
                            changeSelectedNodes(Array.from(ids).sort((a, b) => a - b))
                          }}
                          aria-label={`Узел ${node.name}`}
                        />
                        <div className="min-w-0">
                          <span className="text-sm font-medium">{node.name}</span>
                          <span className="text-[10px] text-muted-foreground">
                            {node.status === 'online' ? 'онлайн' : 'офлайн — создадим при следующем запуске'}
                          </span>
                        </div>
                      </label>
                    )
                  })}
                </div>
              )}
            </div>

            <div className="space-y-1.5">
              <Label>Протоколы</Label>
              <fieldset className="border-none p-0 m-0 flex gap-3">
                <legend className="sr-only">Протоколы</legend>
                {availableProtocols.length === 0 ? (
                  <p className="text-xs text-destructive">
                    Нет включённых VPN-модулей. Включите OpenVPN / WireGuard / AmneziaWG 2.0 в
                    Настройках → Разделы.
                  </p>
                ) : null}
                {availableProtocols.map((proto) => {
                  const checked = selectedProtocols.includes(proto.id)
                  const awg2Disabled = proto.id === 'amneziawg2' && awg2Blocked.length > 0 && !checked
                  return (
                    <label
                      key={proto.id}
                      className={cn(
                        'flex items-center gap-2',
                        awg2Disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
                      )}
                    >
                      <Checkbox
                        checked={checked}
                        disabled={awg2Disabled}
                        onCheckedChange={(next) => {
                          const ids = new Set(selectedProtocols)
                          if (next) ids.add(proto.id)
                          else ids.delete(proto.id)
                          setSelectedProtocols(Array.from(ids))
                        }}
                        aria-label={proto.label}
                      />
                      {proto.label}
                    </label>
                  )
                })}
              </fieldset>
              {awg2Enabled && awg2Blocked.length > 0 ? (
                <p className="text-xs text-muted-foreground">
                  AmneziaWG 2.0: AZ-AWG2 не установлен на: {awg2Blocked.map((n) => n.name).join(', ')}
                </p>
              ) : null}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="createConfigCount">Конфигов (всего имён на все серверы)</Label>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setConfigCount((c) => Math.max(1, c - 1))}
                  disabled={configCount <= 1 || submitting}
                  className="h-8 w-8"
                >
                  −
                </Button>
                <Input
                  id="createConfigCount"
                  type="number"
                  min={1}
                  max={20}
                  value={configCount}
                  onChange={(e) => {
                    const v = Number.parseInt(e.target.value, 10)
                    if (Number.isFinite(v) && v >= 1 && v <= 20) setConfigCount(v)
                  }}
                  className="h-8 w-20 text-center font-mono"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setConfigCount((c) => Math.min(20, c + 1))}
                  disabled={configCount >= 20 || submitting}
                  className="h-8 w-8"
                >
                  +
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                {totalFiles} файл{totalFiles === 1 ? '' : 'а'} на {selectedNodeIds.length} узел{
                  selectedNodeIds.length !== 1 ? 'ах' : ''
                } × {selectedProtocols.length} протокол{selectedProtocols.length === 1 ? '' : 'а'}
              </p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="createAccessUntil">Срок доступа (необязательно)</Label>
              <Input
                id="createAccessUntil"
                type="date"
                value={accessUntil}
                onChange={(e) => setAccessUntil(e.target.value)}
                className="h-9"
              />
              <p className="text-xs text-muted-foreground">
                Пусто — бессрочно. Истёкший срок блокирует применение плана.
              </p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="createConfigQuota">Квота имён на пользователя (необязательно)</Label>
              <Input
                id="createConfigQuota"
                type="number"
                min={0}
                max={1000}
                value={configQuota}
                onChange={(e) => setConfigQuota(e.target.value)}
                placeholder="без лимита"
                className="h-9"
              />
              <p className="text-xs text-muted-foreground">
                Лимит имён конфигов на всех серверах, а не файлов. 0 — общий лимит панели
              </p>
            </div>
          </>
        )}

        {step === 'summary' && mode === 'from_existing' && (
          <>
            {header(
              'Сводка',
              'После создания откроется карточка абонента. VPN-файлы на серверах не создаются.',
            )}
            <div className="rounded-lg border bg-muted/20 p-3 space-y-1">
              <div className="flex items-center gap-2">
                <span className="font-medium">Абонент:</span>
                <span className="font-mono">{username}</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="font-medium shrink-0">Конфиги:</span>
                <span className="font-mono text-[11px]">
                  {selectedConfigNames.length ? selectedConfigNames.join(', ') : 'без привязки'}
                </span>
              </div>
              {accessUntil ? (
                <div className="flex items-center gap-2">
                  <span className="font-medium">Срок доступа:</span>
                  <span className="text-[11px]">{formatDate(accessUntil)}</span>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="font-medium">Срок доступа:</span>
                  <span className="text-[11px]">бессрочно</span>
                </div>
              )}
              {panelLogin && (
                <div className="flex items-center gap-2">
                  <span className="font-medium">Вход в панель:</span>
                  <span className="text-[11px]">включён</span>
                </div>
              )}
            </div>
          </>
        )}

        {step === 'summary' && mode === 'provision' && (
          <>
            {header(
              'Сводка',
              'Проверьте параметры перед созданием. После нажатия «Создать абонента» откроется карточка с ходом задачи.',
            )}
            <div className="space-y-3">
              <div className="rounded-lg border bg-muted/20 p-3">
                <div className="flex items-center gap-2">
                  <span className="font-medium">Абонент:</span>
                  <span className="font-mono">{username}</span>
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <span className="font-medium">Базовое имя:</span>
                  <span className="font-mono">{clientBaseName || '—'}</span>
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <span className="font-medium">Имена конфигов:</span>
                  <span className="font-mono text-[11px]">{planNames.join(', ') || '—'}</span>
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <span className="font-medium">Узлы:</span>
                  <span className="text-[11px]">
                    {selectedNodeIds.length
                      ? nodes.filter((n) => selectedNodeIds.includes(n.id)).map((n) => n.name).join(', ')
                      : '—'}
                  </span>
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <span className="font-medium">Протоколы:</span>
                  <span className="text-[11px]">{selectedProtocols.join(', ') || '—'}</span>
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <span className="font-medium">Файлов всего:</span>
                  <span className="font-mono">{totalFiles}</span>
                </div>
                {accessUntil && (
                  <div className="flex items-center gap-2 mt-1">
                    <span className="font-medium">Срок доступа:</span>
                    <span className="text-[11px]">{formatDate(accessUntil)}</span>
                  </div>
                )}
                {panelLogin && (
                  <div className="flex items-center gap-2 mt-1">
                    <span className="font-medium">Вход в панель:</span>
                    <span className="text-[11px]">включён</span>
                  </div>
                )}
              </div>
              <div className="rounded-lg border border-amber-500/25 bg-amber-500/8 p-3 text-xs text-amber-950 dark:text-amber-100">
                <p className="font-medium">Лимит считается по именам, не по файлам.</p>
                <p className="mt-1">
                  {planNames.length} конфиг{planNames.length === 1 ? '' : 'а'} ×{' '}
                  {selectedProtocols.length} протокола × {selectedNodeIds.length} узел{
                    selectedNodeIds.length !== 1 ? 'а' : ''
                  } = {totalFiles} файл{totalFiles === 1 ? '' : 'а'}. Трафик со всех серверов считается в один
                  общий лимит.
                </p>
              </div>
            </div>
          </>
        )}
      </div>
    </AppDialog>
  )
}
