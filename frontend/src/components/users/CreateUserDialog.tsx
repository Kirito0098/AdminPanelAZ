import { useEffect, useMemo, useState } from 'react'
import { ArrowRight, ChevronLeft, Users as UsersIcon } from 'lucide-react'
import { getNodes } from '@/api/nodes'
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

interface CreateUserDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreate: (data: {
    username: string
    client_base_name: string
    node_ids: number[]
    protocols: string[]
    config_count: number
    config_quota?: number | null
    access_until?: string | null
    panel_login_enabled: boolean
    password?: string | null
    telegram_id?: string | null
    preset_id?: number | null
  }) => void | Promise<void>
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

export default function CreateUserDialog({
  open,
  onOpenChange,
  onCreate,
}: CreateUserDialogProps) {
  const { isEnabled } = useFeatureModules()
  const availableProtocols = useMemo(
    () => PROTOCOLS.filter((p) => protocolEnabled(isEnabled, p.featureKeys)),
    [isEnabled],
  )
  const [step, setStep] = useState<Step>('who')
  const [nodes, setNodes] = useState<Node[]>([])
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

  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) {
      setStep('who')
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
        const list = await getNodes()
        if (!cancelled) setNodes(list)
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
    if (step === 'who') return Boolean(username.trim() && clientBaseName.trim())
    if (step === 'access')
      return selectedNodeIds.length > 0 && selectedProtocols.length > 0
    return true
  }

  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      await onCreate({
        username: username.trim(),
        client_base_name: clientBaseName.trim(),
        node_ids: selectedNodeIds,
        protocols: selectedProtocols,
        config_count: configCount,
        config_quota: configQuota.trim() === '' ? null : Number.parseInt(configQuota, 10) || undefined,
        access_until: accessUntil.trim() === '' ? undefined : accessUntil,
        panel_login_enabled: panelLogin,
        password: panelLogin ? password : undefined,
        telegram_id: telegramId.trim() === '' ? undefined : telegramId.trim(),
        preset_id: selectedPresetId,
      })
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

  return (
    <AppDialog
      open={open}
      onOpenChange={onOpenChange}
      title={step === 'summary' ? 'Сводка создания' : step === 'access' ? 'Доступ' : 'Кто'}
      description={step === 'summary' ? 'Проверьте план перед созданием абонента' : undefined}
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
              'Логин абонента и базовое имя конфигов. Имена конфигов будут client, client-2, …',
            )}
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
            <div className="space-y-1.5">
              <Label htmlFor="createTelegramId">Telegram ID (необязательно)</Label>
              <Input
                id="createTelegramId"
                type="number"
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
            {presets.length > 0 && (
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

        {step === 'access' && (
          <>
            {header(
              'Доступ',
              'Выберите узлы, протоколы и сколько имён конфигов создать на каждом узле.',
            )}
            <div className="space-y-1.5">
              <Label>Узлы</Label>
              {nodesLoading ? (
                <span className="text-xs text-muted-foreground">Загрузка узлов…</span>
              ) : nodes.length === 0 ? (
                <p className="text-xs text-muted-foreground">Узлов нет — добавьте позже в карточке абонента</p>
              ) : (
                <div className="grid gap-1 sm:grid-cols-2">
                  {nodes.map((node) => {
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
                            setSelectedNodeIds(Array.from(ids).sort((a, b) => a - b))
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
                  return (
                    <label key={proto.id} className="flex items-center gap-2 cursor-pointer">
                      <Checkbox
                        checked={checked}
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

        {step === 'summary' && (
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