import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Ban,
  CalendarPlus,
  Gauge,
  Loader2,
  Play,
  Plus,
  Search,
  Trash2,
  UserRound,
} from 'lucide-react'
import { ApiError } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import MiniPageHeader from '@/tg-mini/components/MiniPageHeader'
import {
  createTgProvisionedUser,
  deleteTgUser,
  extendTgUser,
  getTgNodes,
  getTgPanelUsers,
  listTgPresets,
  resetTgUserTraffic,
  resumeTgUser,
  setTgUserTrafficLimit,
  suspendTgUser,
} from '@/tg-mini/api'
import { formatDate } from '@/lib/datetime'
import { formatBytes } from '@/lib/trafficFormat'
import { cn } from '@/lib/utils'
import type { PresetResponse, TgMiniNode, User } from '@/types'

type StatusFilter = 'all' | 'active' | 'suspended' | 'expired'

const STATUS_FILTERS: Array<{ value: StatusFilter; label: string }> = [
  { value: 'all', label: 'Все' },
  { value: 'active', label: 'Активные' },
  { value: 'suspended', label: 'Блок' },
  { value: 'expired', label: 'Истекли' },
]

function isExpired(user: User): boolean {
  if (!user.access_until) return false
  const until = new Date(user.access_until).getTime()
  return Number.isFinite(until) && until < Date.now()
}

function statusOf(user: User): StatusFilter {
  if (user.suspended_at) return 'suspended'
  if (isExpired(user)) return 'expired'
  return 'active'
}

function statusBadge(user: User) {
  const status = statusOf(user)
  if (status === 'suspended') {
    return <Badge variant="destructive">Заблокирован</Badge>
  }
  if (status === 'expired') {
    return <Badge variant="warning">Истёк</Badge>
  }
  return <Badge variant="success">Активен</Badge>
}

function accessLabel(user: User): string {
  if (!user.access_until) return 'бессрочно'
  return `до ${formatDate(user.access_until)}`
}

/** Admin «Клиенты» — аккаунты абонентов (паритет с веб «Пользователи», без QR/CSV). */
export default function Clients() {
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [selected, setSelected] = useState<User | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getTgPanelUsers()
      setUsers(data)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const subscribers = useMemo(() => users.filter((user) => user.role !== 'admin'), [users])

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    return subscribers.filter((user) => {
      if (status !== 'all' && statusOf(user) !== status) return false
      if (!query) return true
      return (
        user.username.toLowerCase().includes(query) ||
        (user.client_base_name ?? '').toLowerCase().includes(query) ||
        (user.telegram_id ?? '').includes(query)
      )
    })
  }, [search, status, subscribers])

  const run = async (action: () => Promise<unknown>, done: string) => {
    setBusy(true)
    setFeedback(null)
    try {
      await action()
      setFeedback(done)
      await load()
    } catch (err) {
      setFeedback(err instanceof ApiError ? err.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="tg-mini-dashboard space-y-3">
      <MiniPageHeader
        title="Клиенты"
        subtitle={`${subscribers.length} абонент${subscribers.length === 1 ? '' : 'ов'}`}
        onRefresh={() => void load()}
        refreshing={loading}
      />

      <Button type="button" className="w-full gap-2" onClick={() => setCreateOpen(true)}>
        <Plus size={18} aria-hidden />
        Создать клиента
      </Button>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="tg-mini-search-wrap">
        <Search size={15} className="tg-mini-search-icon" aria-hidden />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Имя, базовое имя или Telegram ID…"
          className="tg-mini-search-input"
          aria-label="Поиск клиентов"
        />
      </div>

      <div className="tg-mini-segmented" role="tablist" aria-label="Фильтр статуса">
        {STATUS_FILTERS.map((filter) => (
          <button
            key={filter.value}
            type="button"
            role="tab"
            aria-selected={status === filter.value}
            className={cn('tg-mini-segment', status === filter.value && 'is-active')}
            onClick={() => setStatus(filter.value)}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {loading && users.length === 0 ? (
        <div className="tg-mini-skeleton tg-mini-skeleton-section" aria-busy="true" />
      ) : filtered.length === 0 ? (
        <div className="tg-mini-filter-empty">
          <UserRound size={22} className="text-muted-foreground" aria-hidden />
          <p className="text-sm font-medium">Нет клиентов</p>
          <p className="text-xs text-muted-foreground">Измените фильтр или создайте абонента</p>
        </div>
      ) : (
        filtered.map((user) => (
          <Card key={user.id} className="tg-mini-config-card">
            <CardContent className="p-0">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 p-3 text-left hover:bg-muted/50"
                onClick={() => {
                  setSelected(user)
                  setFeedback(null)
                }}
              >
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate font-medium">{user.username}</span>
                    {statusBadge(user)}
                    {user.online && <Badge variant="success">онлайн</Badge>}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {user.client_base_name ?? '—'} · {accessLabel(user)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Трафик: {formatBytes(user.traffic_consumed_bytes ?? 0)}
                    {user.traffic_limit_bytes
                      ? ` из ${formatBytes(user.traffic_limit_bytes)}`
                      : ' · без лимита'}
                  </p>
                </div>
              </button>
            </CardContent>
          </Card>
        ))
      )}

      <ClientActionsDialog
        user={selected}
        busy={busy}
        feedback={feedback}
        onClose={() => setSelected(null)}
        onSuspend={(reason) =>
          selected && void run(() => suspendTgUser(selected.id, reason), 'Клиент заблокирован')
        }
        onResume={() => selected && void run(() => resumeTgUser(selected.id), 'Клиент разблокирован')}
        onExtend={(days) =>
          selected &&
          void run(() => extendTgUser(selected.id, days), `Доступ продлён на ${days} дн.`)
        }
        onLimit={(bytes) =>
          selected &&
          void run(
            () => setTgUserTrafficLimit(selected.id, bytes),
            bytes == null ? 'Лимит снят' : 'Лимит сохранён',
          )
        }
        onResetTraffic={() =>
          selected && void run(() => resetTgUserTraffic(selected.id), 'Счётчик трафика сброшен')
        }
        onDelete={() =>
          selected &&
          void run(async () => {
            await deleteTgUser(selected.id)
            setSelected(null)
          }, 'Клиент удалён')
        }
      />

      <CreateClientDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={() => {
          setCreateOpen(false)
          void load()
        }}
      />
    </div>
  )
}

interface ClientActionsDialogProps {
  user: User | null
  busy: boolean
  feedback: string | null
  onClose: () => void
  onSuspend: (reason: string | null) => void
  onResume: () => void
  onExtend: (days: number) => void
  onLimit: (bytes: number | null) => void
  onResetTraffic: () => void
  onDelete: () => void
}

function ClientActionsDialog({
  user,
  busy,
  feedback,
  onClose,
  onSuspend,
  onResume,
  onExtend,
  onLimit,
  onResetTraffic,
  onDelete,
}: ClientActionsDialogProps) {
  const [reason, setReason] = useState('Заблокирован администратором')
  const [limitGb, setLimitGb] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)

  useEffect(() => {
    setReason('Заблокирован администратором')
    setConfirmDelete(false)
    setLimitGb(
      user?.traffic_limit_bytes ? String(Math.round(user.traffic_limit_bytes / 1024 ** 3)) : '',
    )
  }, [user])

  const suspended = Boolean(user?.suspended_at)

  return (
    <Dialog open={Boolean(user)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogTitle>{user?.username}</DialogTitle>
        <DialogDescription>
          {user ? `${user.client_base_name ?? '—'} · ${accessLabel(user)}` : ''}
        </DialogDescription>

        <div className="space-y-3 pt-2">
          {feedback && <p className="text-sm text-muted-foreground">{feedback}</p>}

          {suspended ? (
            <Button
              type="button"
              className="w-full gap-2"
              disabled={busy}
              onClick={onResume}
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              Разблокировать
            </Button>
          ) : (
            <div className="space-y-1.5">
              <Label htmlFor="suspend-reason">Причина блокировки</Label>
              <Input
                id="suspend-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <Button
                type="button"
                variant="destructive"
                className="w-full gap-2"
                disabled={busy}
                onClick={() => onSuspend(reason.trim() || null)}
              >
                {busy ? <Loader2 size={16} className="animate-spin" /> : <Ban size={16} />}
                Заблокировать все конфиги
              </Button>
            </div>
          )}

          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              className="flex-1 gap-1.5"
              disabled={busy}
              onClick={() => onExtend(30)}
            >
              <CalendarPlus size={15} /> +30 дн.
            </Button>
            <Button
              type="button"
              variant="outline"
              className="flex-1 gap-1.5"
              disabled={busy}
              onClick={() => onExtend(60)}
            >
              <CalendarPlus size={15} /> +60 дн.
            </Button>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="traffic-limit">Лимит трафика, ГБ</Label>
            <div className="flex gap-2">
              <Input
                id="traffic-limit"
                inputMode="numeric"
                value={limitGb}
                onChange={(e) => setLimitGb(e.target.value)}
                placeholder="без лимита"
              />
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => {
                  const gb = Number.parseInt(limitGb, 10)
                  onLimit(Number.isFinite(gb) && gb > 0 ? gb * 1024 ** 3 : null)
                }}
              >
                <Gauge size={15} /> ОК
              </Button>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={busy}
              onClick={onResetTraffic}
            >
              Сбросить счётчик трафика
            </Button>
          </div>

          <Button
            type="button"
            variant="outline"
            className="w-full gap-2 text-destructive"
            disabled={busy}
            onClick={() => {
              if (!confirmDelete) {
                setConfirmDelete(true)
                return
              }
              onDelete()
            }}
          >
            <Trash2 size={15} /> {confirmDelete ? 'Точно удалить?' : 'Удалить клиента'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

interface CreateClientDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: () => void
}

function CreateClientDialog({ open, onOpenChange, onCreated }: CreateClientDialogProps) {
  const [username, setUsername] = useState('')
  const [baseName, setBaseName] = useState('')
  const [presets, setPresets] = useState<PresetResponse[]>([])
  const [presetId, setPresetId] = useState('')
  const [nodes, setNodes] = useState<TgMiniNode[]>([])
  const [nodeIds, setNodeIds] = useState<number[]>([])
  const [protocols, setProtocols] = useState<string[]>(['openvpn', 'wireguard'])
  const [count, setCount] = useState('1')
  const [panelLogin, setPanelLogin] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setUsername('')
    setBaseName('')
    setPresetId('')
    setCount('1')
    setPanelLogin(false)
    setError(null)
    void listTgPresets().then(setPresets).catch(() => setPresets([]))
    void getTgNodes()
      .then((data) => {
        const available = data.nodes.filter(
          (node) => node.ha_role !== 'replica' && (node.node_kind || 'vpn') !== 'proxy',
        )
        setNodes(available)
        setNodeIds(available.filter((node) => node.is_active).map((node) => node.id))
      })
      .catch(() => setNodes([]))
  }, [open])

  useEffect(() => {
    const preset = presets.find((item) => String(item.id) === presetId)
    if (!preset) return
    setNodeIds(preset.node_ids)
    setProtocols(preset.protocols)
    setCount(String(preset.config_count))
  }, [presetId, presets])

  const toggle = (list: string[], value: string, setter: (next: string[]) => void) => {
    setter(list.includes(value) ? list.filter((item) => item !== value) : [...list, value])
  }

  const submit = async () => {
    const name = username.trim()
    if (!name) {
      setError('Укажите логин')
      return
    }
    if (nodeIds.length === 0) {
      setError('Выберите хотя бы один узел')
      return
    }
    if (protocols.length === 0) {
      setError('Выберите хотя бы один протокол')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await createTgProvisionedUser({
        username: name,
        client_base_name: baseName.trim() || name,
        node_ids: nodeIds,
        protocols,
        config_count: Math.max(1, Number.parseInt(count, 10) || 1),
        config_quota: null,
        access_until: null,
        panel_login_enabled: panelLogin,
        password: null,
        telegram_id: null,
      })
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка создания')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogTitle>Создать клиента</DialogTitle>
        <DialogDescription>Логин и план конфигов</DialogDescription>

        <div className="space-y-3 pt-2">
          {presets.length > 0 && (
            <div className="space-y-1.5">
              <Label htmlFor="client-preset">Пресет</Label>
              <select
                id="client-preset"
                value={presetId}
                onChange={(e) => setPresetId(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm"
              >
                <option value="">Вручную</option>
                {presets.map((preset) => (
                  <option key={preset.id} value={preset.id}>
                    {preset.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="client-username">Логин</Label>
            <Input
              id="client-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="off"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="client-base-name">Базовое имя конфигов</Label>
            <Input
              id="client-base-name"
              value={baseName}
              onChange={(e) => setBaseName(e.target.value)}
              placeholder="по умолчанию = логин"
              autoComplete="off"
            />
          </div>

          <div className="space-y-1.5">
            <Label>Узлы</Label>
            <div className="flex flex-wrap gap-1.5">
              {nodes.map((node) => (
                <button
                  key={node.id}
                  type="button"
                  className={cn(
                    'rounded-md border px-2 py-1 text-xs',
                    nodeIds.includes(node.id) ? 'border-primary bg-primary/10' : 'border-border',
                  )}
                  onClick={() => toggle(nodeIds.map(String), String(node.id), (next) => setNodeIds(next.map(Number)))}
                >
                  {node.name}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Протоколы</Label>
            <div className="flex flex-wrap gap-1.5">
              {['openvpn', 'wireguard', 'amneziawg2'].map((protocol) => (
                <button
                  key={protocol}
                  type="button"
                  className={cn(
                    'rounded-md border px-2 py-1 text-xs',
                    protocols.includes(protocol) ? 'border-primary bg-primary/10' : 'border-border',
                  )}
                  onClick={() => toggle(protocols, protocol, setProtocols)}
                >
                  {protocol}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="client-count">Имён конфигов</Label>
            <Input
              id="client-count"
              inputMode="numeric"
              value={count}
              onChange={(e) => setCount(e.target.value)}
            />
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={panelLogin}
              onChange={(e) => setPanelLogin(e.target.checked)}
            />
            Вход в панель
          </label>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <Button type="button" className="w-full" disabled={busy} onClick={() => void submit()}>
            {busy ? <Loader2 size={16} className="animate-spin" /> : 'Создать'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
