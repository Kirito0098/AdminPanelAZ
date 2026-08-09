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
  X,
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
import { SettingsCollapsible, SettingsToolbar } from '@/components/settings/SettingsChrome'
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

function RoleBadge({ role }: { role: UserRole }) {
  return (
    <Badge
      variant={role === 'admin' ? 'default' : 'secondary'}
      className="shrink-0 text-[10px] font-medium"
    >
      {ROLE_LABELS[role] ?? role}
    </Badge>
  )
}

function StatusBadge({ active }: { active: boolean }) {
  return (
    <Badge variant={active ? 'success' : 'destructive'} className="shrink-0 text-[10px] font-medium">
      {active ? 'Активен' : 'Отключён'}
    </Badge>
  )
}

function UserAvatar({ username, size = 'md' }: { username: string; size?: 'sm' | 'md' }) {
  const letter = (username.trim()[0] || '?').toUpperCase()
  return (
    <div
      className={cn(
        'flex shrink-0 items-center justify-center rounded-lg bg-primary/15 font-semibold text-primary',
        size === 'sm' ? 'h-8 w-8 text-xs' : 'h-9 w-9 text-sm',
      )}
    >
      {letter}
    </div>
  )
}

function UserMetaLine({ user }: { user: PanelUser }) {
  const bits: string[] = [`ID ${user.id}`]
  if (user.role === 'user' && user.can_create_configs === false) bits.push('Создание выкл.')
  if (user.role === 'user' && user.config_quota != null && user.config_quota > 0) {
    bits.push(`Квота ${user.config_quota}`)
  }
  return (
    <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{bits.join(' · ')}</p>
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
    <div className="rounded-lg border bg-card px-3 py-3">
      <div className="flex items-start gap-3">
        <UserAvatar username={user.username} size="sm" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm font-medium">{user.username}</span>
            {user.id === currentUserId && (
              <Badge variant="outline" className="text-[10px]">
                вы
              </Badge>
            )}
            <RoleBadge role={user.role} />
            <StatusBadge active={user.is_active} />
          </div>
          <UserMetaLine user={user} />
          <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
            {user.telegram_id ? `TG ${user.telegram_id}` : 'Telegram не привязан'}
          </p>
        </div>
        <div className="flex shrink-0 gap-1">
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onEdit} aria-label="Изменить">
            <Pencil size={14} />
          </Button>
          {user.id !== currentUserId ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Ещё">
                  <MoreHorizontal size={14} />
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
      </div>
    </div>
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
  const [userQuery, setUserQuery] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [policyOpen, setPolicyOpen] = useState(false)
  const [ownerFilter, setOwnerFilter] = useState<string>('all')
  const [activeEditor, setActiveEditor] = useState<PanelUser | null>(null)
  const [draftRole, setDraftRole] = useState<UserRole>('user')
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

  const filteredUsers = useMemo(() => {
    const q = userQuery.trim().toLowerCase()
    if (!q) return usersList
    return usersList.filter((u) => {
      const tg = (u.telegram_id || '').toLowerCase()
      const role = (ROLE_LABELS[u.role] || u.role).toLowerCase()
      return (
        u.username.toLowerCase().includes(q) ||
        tg.includes(q) ||
        role.includes(q) ||
        String(u.id).includes(q)
      )
    })
  }, [usersList, userQuery])

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

  const loadUserConfigAccess = async (userId: number) => {
    setAccessLoading(true)
    try {
      const data = await getUserConfigAccess(userId)
      setDraftGroups(data.config_groups)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить доп. доступ')
    } finally {
      setAccessLoading(false)
    }
  }

  const openUserEditor = async (user: PanelUser) => {
    setActiveEditor(user)
    setDraftRole(user.role)
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
      await loadUserConfigAccess(user.id)
    }
  }

  const changeDraftRole = (role: UserRole) => {
    setDraftRole(role)
    if (role === 'user' && activeEditor && activeEditor.role === 'admin') {
      void loadUserConfigAccess(activeEditor.id)
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
      const payload: Record<string, unknown> = {
        telegram_id: draftTelegramId.trim(),
        role: draftRole,
      }
      if (draftRole === 'user') {
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
      if (draftRole === 'user') {
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
      <SettingsToolbar
        title="Учётные записи"
        count={stats.total}
        meta={`${stats.admins} админ. · ${stats.regular} польз. · ${stats.active} активных`}
        actions={
          <>
            <div className="relative w-full sm:w-64">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={userQuery}
                onChange={(e) => setUserQuery(e.target.value)}
                placeholder="Поиск: логин, роль, Telegram…"
                className="h-9 pl-9"
                aria-label="Поиск пользователей"
              />
              {userQuery ? (
                <button
                  type="button"
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                  onClick={() => setUserQuery('')}
                  aria-label="Очистить поиск"
                >
                  <X size={14} />
                </button>
              ) : null}
            </div>
            <Button
              type="button"
              size="sm"
              className="h-9 shrink-0 gap-1.5"
              onClick={() => setCreateOpen((v) => !v)}
              aria-expanded={createOpen}
            >
              <UserPlus size={15} />
              Добавить
            </Button>
          </>
        }
      />

      {createOpen ? (
        <Card className="border-primary/25 shadow-sm">
          <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0 pb-3">
            <div>
              <CardTitle className="flex items-center gap-2 text-sm">
                <UserPlus size={16} />
                Новый пользователь
              </CardTitle>
              <CardDescription className="mt-1">Логин, пароль и роль доступа к панели</CardDescription>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={() => setCreateOpen(false)}
              aria-label="Скрыть форму"
            >
              <X size={16} />
            </Button>
          </CardHeader>
          <CardContent>
            <form noValidate onSubmit={onCreateUser} className="space-y-3">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_auto_auto] lg:items-end">
                <div className="space-y-1.5">
                  <Label htmlFor="newUsername">Логин</Label>
                  <Input
                    id="newUsername"
                    value={newUsername}
                    onChange={(e) => onNewUsernameChange(e.target.value)}
                    placeholder="username"
                    autoComplete="off"
                    className="h-9"
                    autoFocus
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="newPassword">Пароль</Label>
                  <Input
                    id="newPassword"
                    type="password"
                    value={newPassword}
                    onChange={(e) => onNewPasswordChange(e.target.value)}
                    autoComplete="new-password"
                    className="h-9"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="newRole">Роль</Label>
                  <select
                    id="newRole"
                    value={newRole}
                    onChange={(e) => onNewRoleChange(e.target.value as UserRole)}
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 sm:min-w-[10rem]"
                  >
                    {ROLE_OPTIONS.map(({ id }) => (
                      <option key={id} value={id}>
                        {ROLE_LABELS[id]}
                      </option>
                    ))}
                  </select>
                </div>
                <Button type="submit" size="sm" className="h-9 gap-1.5">
                  <UserPlus size={15} />
                  Создать
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">{ROLE_HINTS[newRole]}</p>
            </form>
          </CardContent>
        </Card>
      ) : null}

      <Card className="shadow-sm">
        <CardContent className="p-0 pt-0">
          {usersList.length === 0 ? (
            <EmptyState
              icon={Users}
              title="Нет пользователей"
              description="Нажмите «Добавить», чтобы создать первую учётную запись"
              className="py-10"
            />
          ) : filteredUsers.length === 0 ? (
            <EmptyState
              icon={Search}
              title="Ничего не найдено"
              description={`Нет совпадений для «${userQuery.trim()}»`}
              className="py-10"
            />
          ) : (
            <ResponsiveDataView
              mobile={filteredUsers.map((u) => (
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
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="h-10 pl-4">Пользователь</TableHead>
                      <TableHead className="h-10">Статус</TableHead>
                      <TableHead className="h-10">Роль</TableHead>
                      <TableHead className="h-10">Telegram</TableHead>
                      <TableHead className="h-10 pr-4 text-right"> </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredUsers.map((u) => (
                      <TableRow key={u.id} className="group">
                        <TableCell className="py-2.5 pl-4">
                          <div className="flex items-center gap-2.5">
                            <UserAvatar username={u.username} size="sm" />
                            <div className="min-w-0">
                              <div className="flex items-center gap-1.5">
                                <span className="truncate text-sm font-medium">{u.username}</span>
                                {u.id === currentUserId ? (
                                  <Badge variant="outline" className="text-[10px]">
                                    вы
                                  </Badge>
                                ) : null}
                              </div>
                              <UserMetaLine user={u} />
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className="py-2.5">
                          <StatusBadge active={u.is_active} />
                        </TableCell>
                        <TableCell className="py-2.5">
                          <RoleBadge role={u.role} />
                        </TableCell>
                        <TableCell className="py-2.5 font-mono text-xs text-muted-foreground">
                          {u.telegram_id || '—'}
                        </TableCell>
                        <TableCell className="py-2.5 pr-3 text-right">
                          <div className="flex justify-end gap-0.5 opacity-80 transition-opacity group-hover:opacity-100">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => void openUserEditor(u)}
                              aria-label={`Изменить ${u.username}`}
                            >
                              <Pencil size={14} />
                            </Button>
                            {u.id !== currentUserId ? (
                              <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-8 w-8"
                                    aria-label={`Действия ${u.username}`}
                                  >
                                    <MoreHorizontal size={14} />
                                  </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end">
                                  <DropdownMenuItem
                                    className="text-destructive focus:text-destructive"
                                    onClick={() => onDeleteUser(u.id, u.username)}
                                  >
                                    <Trash2 size={14} />
                                    Удалить
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                            ) : null}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              }
              mobileClassName="space-y-2 p-3"
              desktopClassName="overflow-x-auto"
            />
          )}
        </CardContent>
      </Card>

      <SettingsCollapsible
        open={policyOpen}
        onOpenChange={setPolicyOpen}
        title="Видимость VPN-профилей по умолчанию"
        description="Что видят обычные пользователи без персонального исключения"
        icon={<EyeOff size={16} />}
      >
        {defaultPolicyLoading ? (
          <Spinner label="Загрузка политики..." className="py-4" />
        ) : (
          <>
            <VpnVisibilityPolicyEditor value={defaultPolicy} onChange={setDefaultPolicy} />
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                size="sm"
                onClick={() => void saveDefaultVisibility()}
                disabled={savingDefaultPolicy}
              >
                <Save size={15} />
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
      </SettingsCollapsible>

      <AppDialog
        open={activeEditor !== null}
        onOpenChange={(open) => {
          if (!open && !savingUser) setActiveEditor(null)
        }}
        title={activeEditor ? `Пользователь: ${activeEditor.username}` : 'Пользователь'}
        description="Роль, права доступа, квота и видимость VPN-профилей"
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
                  <RoleBadge role={draftRole} />
                </div>
              </div>
            </div>
          )}

          <div className="space-y-2 rounded-xl border bg-muted/20 p-3">
            <Label>Роль</Label>
            <div className="flex flex-wrap gap-2">
              {ROLE_OPTIONS.map(({ id, icon: Icon }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => changeDraftRole(id)}
                  disabled={savingUser}
                  className={cn(
                    'inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-all',
                    draftRole === id
                      ? 'border-primary bg-primary/10 text-primary ring-1 ring-primary'
                      : 'hover:border-muted-foreground/30 hover:bg-muted/50',
                  )}
                >
                  <Icon size={14} />
                  {ROLE_LABELS[id]}
                </button>
              ))}
            </div>
            <p className="text-xs leading-relaxed text-muted-foreground">{ROLE_HINTS[draftRole]}</p>
          </div>

          {draftRole === 'user' ? (
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
