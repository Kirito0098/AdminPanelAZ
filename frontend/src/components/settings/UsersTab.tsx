import { FormEvent, useEffect, useMemo, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  MoreHorizontal,
  Pencil,
  Save,
  Search,
  Shield,
  Trash2,
  User,
  UserPlus,
  Users,
  EyeOff,
} from 'lucide-react'
import { ApiError, getConfigs, getUserConfigAccess, getUserVpnVisibilityDefault, setUserConfigAccess, setUserVpnVisibilityDefault, updateUser } from '@/api/client'
import AppDialog from '@/components/shared/AppDialog'
import ResponsiveDataView from '@/components/shared/ResponsiveDataView'
import VpnVisibilityPolicyEditor, {
  copyVisibleVpnPolicy,
  FULL_VISIBLE_VPN_POLICY,
  isVisibleVpnPolicyEmpty,
} from '@/components/settings/VpnVisibilityPolicyEditor'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useNotifications } from '@/context/NotificationContext'
import { ROLE_HINTS, ROLE_LABELS } from '@/components/settings/settingsLabels'
import { cn } from '@/lib/utils'
import type { User as PanelUser, UserRole, VisibleVpnProfilesPolicy, VpnConfig } from '@/types'

interface UsersTabProps {
  users: PanelUser[]
  currentUserId?: number
  newUsername: string
  newPassword: string
  newRole: UserRole
  onNewUsernameChange: (value: string) => void
  onNewPasswordChange: (value: string) => void
  onNewRoleChange: (role: UserRole) => void
  onCreateUser: (e: FormEvent) => void
  onDeleteUser: (id: number, name: string) => void
}

const ROLE_OPTIONS: { id: UserRole; icon: LucideIcon }[] = [
  { id: 'user', icon: User },
  { id: 'admin', icon: Shield },
]

function SectionHeading({ title, description }: { title: string; description: string }) {
  return (
    <div className="md:col-span-2">
      <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
      <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
    </div>
  )
}

function MetricPill({
  icon: Icon,
  label,
  value,
  tone = 'default',
}: {
  icon: LucideIcon
  label: string
  value: string
  tone?: 'default' | 'success' | 'muted'
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-card/80 p-3 shadow-sm backdrop-blur-sm">
      <div
        className={cn(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl',
          tone === 'success' && 'bg-primary/15 text-primary',
          tone === 'muted' && 'bg-muted text-muted-foreground',
          tone === 'default' && 'bg-muted/80 text-foreground',
        )}
      >
        <Icon size={18} />
      </div>
      <div className="min-w-0">
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="truncate text-sm font-semibold">{value}</p>
      </div>
    </div>
  )
}

function RoleBadge({ role }: { role: UserRole }) {
  return (
    <Badge
      variant={role === 'admin' ? 'default' : 'secondary'}
      className="shrink-0"
    >
      {ROLE_LABELS[role] ?? role}
    </Badge>
  )
}

function UserAvatar({ username }: { username: string }) {
  const letter = (username.trim()[0] || '?').toUpperCase()
  return (
    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-sm font-semibold text-primary">
      {letter}
    </div>
  )
}

function UserMetaLine({ user }: { user: PanelUser }) {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
      <span>ID {user.id}</span>
      {user.telegram_id ? (
        <span className="font-mono">TG {user.telegram_id}</span>
      ) : (
        <span>Telegram не привязан</span>
      )}
      {user.role === 'user' && user.can_create_configs === false && (
        <span>Создание выключено</span>
      )}
      {user.role === 'user' && user.config_quota != null && user.config_quota > 0 && (
        <span>Квота: {user.config_quota}</span>
      )}
    </div>
  )
}

function UserNameLine({ user, currentUserId }: { user: PanelUser; currentUserId?: number }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="font-medium">{user.username}</span>
      {user.id === currentUserId && (
        <Badge variant="default" className="text-[10px]">
          вы
        </Badge>
      )}
      <RoleBadge role={user.role} />
      <Badge variant={user.is_active ? 'success' : 'destructive'} className="text-[10px]">
        {user.is_active ? 'Активен' : 'Отключён'}
      </Badge>
    </div>
  )
}

function UserCard({
  user,
  currentUserId,
  onEdit,
  onDelete,
}: {
  user: PanelUser
  currentUserId?: number
  onEdit: () => void
  onDelete: () => void
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start gap-3">
        <UserAvatar username={user.username} />
        <div className="min-w-0 flex-1">
          <UserNameLine user={user} currentUserId={currentUserId} />
          <UserMetaLine user={user} />
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="outline" size="sm" className="gap-1.5" onClick={onEdit}>
          <Pencil size={14} />
          Изменить
        </Button>
        {user.id !== currentUserId ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="gap-1.5">
                <MoreHorizontal size={14} />
                Ещё
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onClick={onDelete}
              >
                <Trash2 size={14} />
                Удалить
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>
    </Card>
  )
}

export default function UsersTab({
  users,
  currentUserId,
  newUsername,
  newPassword,
  newRole,
  onNewUsernameChange,
  onNewPasswordChange,
  onNewRoleChange,
  onCreateUser,
  onDeleteUser,
}: UsersTabProps) {
  const { success, error: notifyError } = useNotifications()
  const [configs, setConfigs] = useState<VpnConfig[]>([])
  const [configsLoading, setConfigsLoading] = useState(true)
  const [draftGroups, setDraftGroups] = useState<string[]>([])
  const [accessLoading, setAccessLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [ownerFilter, setOwnerFilter] = useState<string>('all')
  const [activeEditor, setActiveEditor] = useState<PanelUser | null>(null)
  const [draftTelegramId, setDraftTelegramId] = useState('')
  const [draftConfigQuota, setDraftConfigQuota] = useState('')
  const [draftCanCreate, setDraftCanCreate] = useState(true)
  const [savingUser, setSavingUser] = useState(false)
  const [usersList, setUsersList] = useState(users)
  const [defaultPolicy, setDefaultPolicy] = useState<VisibleVpnProfilesPolicy>(FULL_VISIBLE_VPN_POLICY)
  const [defaultPolicyLoading, setDefaultPolicyLoading] = useState(true)
  const [savingDefaultPolicy, setSavingDefaultPolicy] = useState(false)
  const [draftUseCustomVisibility, setDraftUseCustomVisibility] = useState(false)
  const [draftVisibilityPolicy, setDraftVisibilityPolicy] =
    useState<VisibleVpnProfilesPolicy>(FULL_VISIBLE_VPN_POLICY)

  useEffect(() => {
    setUsersList(users)
  }, [users])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      setDefaultPolicyLoading(true)
      try {
        const data = await getUserVpnVisibilityDefault()
        if (!cancelled) setDefaultPolicy(copyVisibleVpnPolicy(data.policy))
      } catch (err) {
        if (!cancelled) {
          notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить умолчание видимости профилей')
        }
      } finally {
        if (!cancelled) setDefaultPolicyLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [notifyError])

  const stats = useMemo(
    () => ({
      total: usersList.length,
      admins: usersList.filter((u) => u.role === 'admin').length,
      regular: usersList.filter((u) => u.role === 'user').length,
      active: usersList.filter((u) => u.is_active).length,
    }),
    [usersList],
  )

  const clientEntries = useMemo(() => {
    const byName = new Map<
      string,
      { name: string; ownerIds: Set<number>; owners: Set<string>; types: Set<string> }
    >()
    for (const cfg of configs) {
      const name = cfg.client_name
      let entry = byName.get(name)
      if (!entry) {
        entry = { name, ownerIds: new Set(), owners: new Set(), types: new Set() }
        byName.set(name, entry)
      }
      if (cfg.owner_id != null) entry.ownerIds.add(cfg.owner_id)
      const ownerLabel = (cfg.owner_username || '').trim()
      if (ownerLabel) entry.owners.add(ownerLabel)
      entry.types.add(cfg.vpn_type)
    }
    return Array.from(byName.values())
      .map((entry) => ({
        name: entry.name,
        ownerIds: Array.from(entry.ownerIds),
        ownerLabel: Array.from(entry.owners).sort((a, b) => a.localeCompare(b, 'ru')).join(', ') || '—',
        types: Array.from(entry.types),
      }))
      .sort((a, b) => a.name.localeCompare(b.name, 'ru'))
  }, [configs])

  const ownerOptions = useMemo(() => {
    const map = new Map<number, string>()
    for (const cfg of configs) {
      if (cfg.owner_id == null) continue
      const label = (cfg.owner_username || '').trim() || `ID ${cfg.owner_id}`
      if (!map.has(cfg.owner_id)) map.set(cfg.owner_id, label)
    }
    return Array.from(map.entries())
      .map(([id, label]) => ({ id, label }))
      .sort((a, b) => a.label.localeCompare(b.label, 'ru'))
  }, [configs])

  const filteredGroups = useMemo(() => {
    const q = search.trim().toLowerCase()
    return clientEntries.filter((entry) => {
      if (ownerFilter === 'none') {
        if (entry.ownerIds.length > 0) return false
      } else if (ownerFilter !== 'all') {
        const ownerId = Number.parseInt(ownerFilter, 10)
        if (!Number.isFinite(ownerId) || !entry.ownerIds.includes(ownerId)) return false
      }
      if (!q) return true
      return (
        entry.name.toLowerCase().includes(q) ||
        entry.ownerLabel.toLowerCase().includes(q)
      )
    })
  }, [clientEntries, search, ownerFilter])

  useEffect(() => {
    let cancelled = false
    const loadConfigs = async () => {
      setConfigsLoading(true)
      try {
        const data = await getConfigs()
        if (!cancelled) setConfigs(data)
      } catch (err) {
        if (!cancelled) {
          notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить конфиги')
        }
      } finally {
        if (!cancelled) setConfigsLoading(false)
      }
    }
    void loadConfigs()
    return () => {
      cancelled = true
    }
  }, [notifyError])

  const openUserEditor = async (user: PanelUser) => {
    setActiveEditor(user)
    setDraftTelegramId(user.telegram_id || '')
    setDraftConfigQuota(
      user.config_quota != null && user.config_quota > 0 ? String(user.config_quota) : '',
    )
    setDraftCanCreate(user.can_create_configs !== false)
    const hasOverride = user.visible_vpn_profiles != null
    setDraftUseCustomVisibility(hasOverride)
    setDraftVisibilityPolicy(
      copyVisibleVpnPolicy(hasOverride ? user.visible_vpn_profiles : defaultPolicy),
    )
    setDraftGroups([])
    setSearch('')
    setOwnerFilter('all')
    if (user.role === 'user') {
      setAccessLoading(true)
      try {
        const data = await getUserConfigAccess(user.id)
        setDraftGroups(data.config_groups)
      } catch (err) {
        notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить доп. доступ')
      } finally {
        setAccessLoading(false)
      }
    }
  }

  const toggleGroup = (name: string, checked: boolean) => {
    setDraftGroups((prev) => {
      if (checked) return prev.includes(name) ? prev : [...prev, name]
      return prev.filter((g) => g !== name)
    })
  }

  const saveDefaultVisibility = async () => {
    setSavingDefaultPolicy(true)
    try {
      const data = await setUserVpnVisibilityDefault(defaultPolicy)
      setDefaultPolicy(copyVisibleVpnPolicy(data.policy))
      success('Умолчание видимости профилей сохранено')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения умолчания')
    } finally {
      setSavingDefaultPolicy(false)
    }
  }

  const saveUserTelegramId = async () => {
    if (!activeEditor) return
    setSavingUser(true)
    try {
      const payload: Record<string, unknown> = { telegram_id: draftTelegramId.trim() }
      if (activeEditor.role === 'user') {
        payload.can_create_configs = draftCanCreate
        const raw = draftConfigQuota.trim()
        payload.config_quota = raw === '' ? 0 : Number.parseInt(raw, 10)
        if (raw !== '' && (!Number.isFinite(payload.config_quota as number) || (payload.config_quota as number) < 0)) {
          notifyError('Квота: целое число ≥ 0 (0 = без лимита по умолчанию)')
          return
        }
        payload.visible_vpn_profiles = draftUseCustomVisibility
          ? draftVisibilityPolicy
          : null
      }
      const updated = await updateUser(activeEditor.id, payload)
      if (activeEditor.role === 'user') {
        await setUserConfigAccess(activeEditor.id, draftGroups)
      }
      setUsersList((prev) => prev.map((item) => (item.id === updated.id ? updated : item)))
      success(`Данные «${updated.username}» сохранены`)
      setActiveEditor(null)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения пользователя')
    } finally {
      setSavingUser(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2 md:items-start">
        <div className="relative overflow-hidden rounded-xl border bg-gradient-to-br from-primary/5 via-card to-card p-4 md:col-span-2">
          <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-primary/10 blur-2xl" />
          <div className="relative grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricPill icon={Users} label="Всего" value={String(stats.total)} tone={stats.total > 0 ? 'default' : 'muted'} />
            <MetricPill
              icon={Shield}
              label="Администраторы"
              value={String(stats.admins)}
              tone={stats.admins > 0 ? 'success' : 'muted'}
            />
            <MetricPill
              icon={User}
              label="Пользователи"
              value={String(stats.regular)}
              tone={stats.regular > 0 ? 'default' : 'muted'}
            />
            <MetricPill
              icon={User}
              label="Активных"
              value={String(stats.active)}
              tone={stats.active > 0 ? 'success' : 'muted'}
            />
          </div>
        </div>

        <SectionHeading
          title="Новая учётная запись"
          description="Логин, пароль и уровень доступа к панели"
        />

        <Card className="overflow-hidden shadow-sm md:col-span-2">
          <div className="h-1 bg-gradient-to-r from-primary/80 to-primary/15" />
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <UserPlus size={18} />
              Создать пользователя
            </CardTitle>
            <CardDescription>Добавьте учётную запись с нужной ролью</CardDescription>
          </CardHeader>
          <CardContent>
            <form noValidate onSubmit={onCreateUser} className="space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <div className="space-y-2">
                  <Label htmlFor="newUsername">Логин</Label>
                  <Input
                    id="newUsername"
                    value={newUsername}
                    onChange={(e) => onNewUsernameChange(e.target.value)}
                    placeholder="username"
                    autoComplete="off"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="newPassword">Пароль</Label>
                  <Input
                    id="newPassword"
                    type="password"
                    value={newPassword}
                    onChange={(e) => onNewPasswordChange(e.target.value)}
                    autoComplete="new-password"
                  />
                </div>
                <div className="flex items-end">
                  <Button type="submit" className="w-full sm:w-auto">
                    <UserPlus size={16} />
                    Добавить
                  </Button>
                </div>
              </div>

              <div className="space-y-2 rounded-xl border bg-muted/20 p-4">
                <Label>Роль</Label>
                <div className="flex flex-wrap gap-2">
                  {ROLE_OPTIONS.map(({ id, icon: Icon }) => (
                    <button
                      key={id}
                      type="button"
                      onClick={() => onNewRoleChange(id)}
                      className={cn(
                        'inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-all',
                        newRole === id
                          ? 'border-primary bg-primary/10 text-primary ring-1 ring-primary'
                          : 'hover:border-muted-foreground/30 hover:bg-muted/50',
                      )}
                    >
                      <Icon size={14} />
                      {ROLE_LABELS[id]}
                    </button>
                  ))}
                </div>
                <p className="text-xs leading-relaxed text-muted-foreground">{ROLE_HINTS[newRole]}</p>
              </div>
            </form>
          </CardContent>
        </Card>

        <SectionHeading
          title="Умолчание видимости профилей"
          description="Какие варианты VPN видят обычные пользователи без персонального исключения"
        />

        <Card className="overflow-hidden shadow-sm md:col-span-2">
          <div className="h-1 bg-gradient-to-r from-emerald-500/70 to-emerald-500/15" />
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <EyeOff size={18} />
              Каталог профилей по умолчанию
            </CardTitle>
            <CardDescription>
              Маршруты AZ/VPN, группы OpenVPN и протоколы для всех пользователей с ролью «Пользователь»
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {defaultPolicyLoading ? (
              <Spinner label="Загрузка политики..." className="py-6" />
            ) : (
              <>
                <VpnVisibilityPolicyEditor value={defaultPolicy} onChange={setDefaultPolicy} />
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    type="button"
                    onClick={() => void saveDefaultVisibility()}
                    disabled={savingDefaultPolicy}
                  >
                    <Save size={16} />
                    {savingDefaultPolicy ? 'Сохранение...' : 'Сохранить умолчание'}
                  </Button>
                  {isVisibleVpnPolicyEmpty(defaultPolicy) && (
                    <span className="text-xs text-amber-700 dark:text-amber-300">
                      Пустой каталог — пользователи не увидят профили
                    </span>
                  )}
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <SectionHeading
          title="Учётные записи"
          description={
            usersList.length > 0
              ? `${usersList.length} пользовател${usersList.length === 1 ? 'ь' : usersList.length < 5 ? 'я' : 'ей'} в системе`
              : 'Список пуст — создайте первого пользователя'
          }
        />

        <Card className="overflow-hidden shadow-sm md:col-span-2">
          <div className="h-1 bg-gradient-to-r from-sky-500/70 to-sky-500/15" />
          <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0 pb-3">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <Users size={18} />
                Список пользователей
              </CardTitle>
              <CardDescription className="mt-1.5">Редактирование Telegram ID и управление доступом</CardDescription>
            </div>
            {usersList.length > 0 && (
              <Badge variant="secondary" className="shrink-0">
                {usersList.length}
              </Badge>
            )}
          </CardHeader>
          <CardContent>
            {usersList.length === 0 ? (
              <EmptyState
                icon={Users}
                title="Нет пользователей"
                description="Создайте первую учётную запись с помощью формы выше"
                className="py-8"
              />
            ) : (
              <ResponsiveDataView
                mobile={usersList.map((u) => (
                  <UserCard
                    key={u.id}
                    user={u}
                    currentUserId={currentUserId}
                    onEdit={() => void openUserEditor(u)}
                    onDelete={() => onDeleteUser(u.id, u.username)}
                  />
                ))}
                desktop={
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Пользователь</TableHead>
                        <TableHead>Роль</TableHead>
                        <TableHead>Telegram</TableHead>
                        <TableHead className="text-right">Действия</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {usersList.map((u) => (
                        <TableRow key={u.id}>
                          <TableCell>
                            <div className="flex items-center gap-3">
                              <UserAvatar username={u.username} />
                              <div className="min-w-0">
                                <UserNameLine user={u} currentUserId={currentUserId} />
                                <UserMetaLine user={u} />
                              </div>
                            </div>
                          </TableCell>
                          <TableCell>
                            <RoleBadge role={u.role} />
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {u.telegram_id || '—'}
                          </TableCell>
                          <TableCell className="text-right">
                            <div className="flex flex-wrap justify-end gap-1">
                              <Button
                                variant="outline"
                                size="sm"
                                className="gap-1.5"
                                onClick={() => void openUserEditor(u)}
                              >
                                <Pencil size={14} />
                                Изменить
                              </Button>
                              {u.id !== currentUserId && (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  className="gap-1.5 border-destructive/30 text-destructive hover:bg-destructive/10"
                                  onClick={() => onDeleteUser(u.id, u.username)}
                                >
                                  <Trash2 size={14} />
                                  Удалить
                                </Button>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                }
                mobileClassName="space-y-3"
                desktopClassName="overflow-x-auto rounded-md border"
              />
            )}
          </CardContent>
        </Card>
      </div>

      <AppDialog
        open={activeEditor !== null}
        onOpenChange={(open) => {
          if (!open && !savingUser) setActiveEditor(null)
        }}
        title={activeEditor ? `Пользователь: ${activeEditor.username}` : 'Пользователь'}
        description="Права доступа, квота и видимость VPN-профилей"
        icon={Users}
        size="xl"
        bodyClassName="px-5 py-4"
        footer={
          <>
            <Button variant="outline" onClick={() => setActiveEditor(null)} disabled={savingUser}>
              Отмена
            </Button>
            <Button onClick={() => void saveUserTelegramId()} disabled={savingUser}>
              <Save size={16} />
              {savingUser ? 'Сохранение...' : 'Сохранить'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {activeEditor && (
            <div className="flex items-center gap-3 rounded-xl border bg-muted/20 px-3 py-2.5">
              <UserAvatar username={activeEditor.username} />
              <div className="min-w-0">
                <p className="font-medium leading-tight">{activeEditor.username}</p>
                <div className="mt-1">
                  <RoleBadge role={activeEditor.role} />
                </div>
              </div>
            </div>
          )}

          {activeEditor?.role === 'user' ? (
            <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
              <div className="space-y-3">
                <div className="space-y-1.5 rounded-xl border bg-muted/20 p-3">
                  <Label htmlFor="editTelegramId">Telegram ID</Label>
                  <Input
                    id="editTelegramId"
                    value={draftTelegramId}
                    onChange={(e) => setDraftTelegramId(e.target.value)}
                    placeholder="123456789"
                    className="font-mono"
                  />
                  <p className="text-xs text-muted-foreground">
                    Пусто — снять привязку. Один ID нельзя назначить двум пользователям.
                  </p>
                </div>
                <div className="flex items-center justify-between gap-3 rounded-xl border bg-muted/20 p-3">
                  <div className="space-y-0.5">
                    <Label htmlFor="editCanCreate">Может создавать конфигурации</Label>
                    <p className="text-xs text-muted-foreground">
                      Выкл. — только просмотр и скачивание (свои и по белому списку).
                    </p>
                  </div>
                  <Switch id="editCanCreate" checked={draftCanCreate} onCheckedChange={setDraftCanCreate} />
                </div>
                <div className="space-y-1.5 rounded-xl border bg-muted/20 p-3">
                  <Label htmlFor="editConfigQuota">Квота конфигов</Label>
                  <Input
                    id="editConfigQuota"
                    type="number"
                    min={0}
                    max={1000}
                    value={draftConfigQuota}
                    onChange={(e) => setDraftConfigQuota(e.target.value)}
                    placeholder="по умолчанию"
                    disabled={!draftCanCreate}
                  />
                  <p className="text-xs text-muted-foreground">
                    {draftCanCreate
                      ? 'Максимум создаваемых VPN-клиентов. Пусто — общий лимит панели.'
                      : 'Квота не применяется, пока создание выключено.'}
                  </p>
                </div>
                <div className="space-y-2 rounded-xl border bg-muted/20 p-3">
                  <div>
                    <Label>Видимость VPN-профилей</Label>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Исключение полностью заменяет глобальное умолчание.
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setDraftUseCustomVisibility(false)
                        setDraftVisibilityPolicy(copyVisibleVpnPolicy(defaultPolicy))
                      }}
                      className={cn(
                        'rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors',
                        !draftUseCustomVisibility
                          ? 'border-primary bg-primary/10 text-primary'
                          : 'hover:bg-muted/50',
                      )}
                    >
                      Как умолчание
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setDraftUseCustomVisibility(true)
                        if (!draftUseCustomVisibility) {
                          setDraftVisibilityPolicy(copyVisibleVpnPolicy(defaultPolicy))
                        }
                      }}
                      className={cn(
                        'rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors',
                        draftUseCustomVisibility
                          ? 'border-primary bg-primary/10 text-primary'
                          : 'hover:bg-muted/50',
                      )}
                    >
                      Своя политика
                    </button>
                  </div>
                  {draftUseCustomVisibility && (
                    <VpnVisibilityPolicyEditor
                      value={draftVisibilityPolicy}
                      onChange={setDraftVisibilityPolicy}
                    />
                  )}
                </div>
              </div>

              <div className="flex min-h-[22rem] flex-col space-y-2 rounded-xl border bg-muted/20 p-3 lg:min-h-[28rem]">
                <div>
                  <Label>Доп. доступ к клиентам</Label>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Чужие VPN-клиенты для просмотра и скачивания без смены владельца. Удалять их нельзя.
                  </p>
                </div>
                {accessLoading || configsLoading ? (
                  <Spinner label="Загрузка клиентов..." className="flex-1 py-8" />
                ) : (
                  <>
                    <div className="grid shrink-0 gap-2 sm:grid-cols-2">
                      <div className="relative">
                        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                        <Input
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                          placeholder="Поиск по имени или владельцу..."
                          className="pl-9"
                        />
                      </div>
                      <select
                        value={ownerFilter}
                        onChange={(e) => setOwnerFilter(e.target.value)}
                        className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                        aria-label="Фильтр по владельцу"
                      >
                        <option value="all">Все владельцы</option>
                        <option value="none">Без владельца</option>
                        {ownerOptions.map((opt) => (
                          <option key={opt.id} value={String(opt.id)}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    {clientEntries.length === 0 ? (
                      <p className="text-sm text-muted-foreground">Конфиги не найдены на активном узле</p>
                    ) : filteredGroups.length === 0 ? (
                      <p className="text-sm text-muted-foreground">Ничего не найдено</p>
                    ) : (
                      <div className="min-h-0 flex-1 space-y-1 overflow-y-auto rounded-xl border bg-card/40 p-1.5">
                        {filteredGroups.map((entry) => {
                          const checked = draftGroups.includes(entry.name)
                          return (
                            <label
                              key={entry.name}
                              className={cn(
                                'flex cursor-pointer items-center gap-3 rounded-lg border px-2.5 py-1.5 transition-colors',
                                checked
                                  ? 'border-primary/30 bg-primary/5'
                                  : 'border-transparent hover:bg-muted/50',
                              )}
                            >
                              <Checkbox
                                checked={checked}
                                onCheckedChange={(next) => toggleGroup(entry.name, next)}
                                aria-label={`Доступ к ${entry.name}`}
                              />
                              <span className="min-w-0 flex-1">
                                <span className="block text-sm font-medium leading-tight">{entry.name}</span>
                                <span className="block truncate text-[11px] text-muted-foreground">
                                  {entry.ownerLabel}
                                </span>
                              </span>
                              <span className="flex shrink-0 gap-1">
                                {entry.types.map((t) => (
                                  <Badge key={t} variant="outline" className="text-[10px]">
                                    {t}
                                  </Badge>
                                ))}
                              </span>
                            </label>
                          )
                        })}
                      </div>
                    )}
                    <p className="shrink-0 text-xs text-muted-foreground">
                      Показано: {filteredGroups.length}
                      {filteredGroups.length !== clientEntries.length ? ` из ${clientEntries.length}` : ''}
                      {' · '}
                      Выбрано: {draftGroups.length}
                    </p>
                  </>
                )}
              </div>
            </div>
          ) : (
            <div className="space-y-1.5 rounded-xl border bg-muted/20 p-3">
              <Label htmlFor="editTelegramId">Telegram ID</Label>
              <Input
                id="editTelegramId"
                value={draftTelegramId}
                onChange={(e) => setDraftTelegramId(e.target.value)}
                placeholder="123456789"
                className="font-mono"
              />
              <p className="text-xs text-muted-foreground">
                Пусто — снять привязку. Один ID нельзя назначить двум пользователям.
              </p>
            </div>
          )}
        </div>
      </AppDialog>

    </div>
  )
}
