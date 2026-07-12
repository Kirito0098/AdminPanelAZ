import { FormEvent, useEffect, useMemo, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Eye,
  MoreHorizontal,
  Pencil,
  Save,
  Search,
  Shield,
  Trash2,
  User,
  UserPlus,
  Users,
} from 'lucide-react'
import { ApiError, getConfigs, getViewerAccess, setViewerAccess, updateUser } from '@/api/client'
import AppDialog from '@/components/shared/AppDialog'
import ResponsiveDataView from '@/components/shared/ResponsiveDataView'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
import type { User as PanelUser, UserRole, VpnConfig } from '@/types'

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
  { id: 'viewer', icon: Eye },
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
      variant={role === 'admin' ? 'default' : role === 'viewer' ? 'outline' : 'secondary'}
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
  const [accessMap, setAccessMap] = useState<Record<number, string[]>>({})
  const [activeViewer, setActiveViewer] = useState<PanelUser | null>(null)
  const [draftGroups, setDraftGroups] = useState<string[]>([])
  const [accessLoading, setAccessLoading] = useState(false)
  const [savingAccess, setSavingAccess] = useState(false)
  const [search, setSearch] = useState('')
  const [activeEditor, setActiveEditor] = useState<PanelUser | null>(null)
  const [draftTelegramId, setDraftTelegramId] = useState('')
  const [draftConfigQuota, setDraftConfigQuota] = useState('')
  const [savingUser, setSavingUser] = useState(false)
  const [usersList, setUsersList] = useState(users)

  useEffect(() => {
    setUsersList(users)
  }, [users])

  const viewerUsers = useMemo(() => users.filter((u) => u.role === 'viewer'), [users])

  const stats = useMemo(
    () => ({
      total: usersList.length,
      admins: usersList.filter((u) => u.role === 'admin').length,
      viewers: usersList.filter((u) => u.role === 'viewer').length,
      active: usersList.filter((u) => u.is_active).length,
    }),
    [usersList],
  )

  const clientGroups = useMemo(() => {
    const names = new Set<string>()
    for (const cfg of configs) {
      names.add(cfg.client_name)
    }
    return Array.from(names).sort((a, b) => a.localeCompare(b, 'ru'))
  }, [configs])

  const filteredGroups = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return clientGroups
    return clientGroups.filter((name) => name.toLowerCase().includes(q))
  }, [clientGroups, search])

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

  useEffect(() => {
    if (viewerUsers.length === 0) {
      setAccessMap({})
      return
    }
    let cancelled = false
    const loadAccess = async () => {
      try {
        const entries = await Promise.all(
          viewerUsers.map(async (u) => {
            const data = await getViewerAccess(u.id)
            return [u.id, data.config_groups] as const
          }),
        )
        if (!cancelled) {
          setAccessMap(Object.fromEntries(entries))
        }
      } catch (err) {
        if (!cancelled) {
          notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить доступ viewer')
        }
      }
    }
    void loadAccess()
    return () => {
      cancelled = true
    }
  }, [viewerUsers, notifyError])

  const openViewerDialog = async (user: PanelUser) => {
    setActiveViewer(user)
    setSearch('')
    setAccessLoading(true)
    try {
      const data = await getViewerAccess(user.id)
      setDraftGroups(data.config_groups)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить доступ')
      setActiveViewer(null)
    } finally {
      setAccessLoading(false)
    }
  }

  const toggleGroup = (name: string, checked: boolean) => {
    setDraftGroups((prev) => {
      if (checked) return prev.includes(name) ? prev : [...prev, name]
      return prev.filter((g) => g !== name)
    })
  }

  const saveViewerAccess = async () => {
    if (!activeViewer) return
    setSavingAccess(true)
    try {
      await setViewerAccess(activeViewer.id, draftGroups)
      setAccessMap((prev) => ({ ...prev, [activeViewer.id]: draftGroups }))
      success(`Доступ для «${activeViewer.username}» сохранён`)
      setActiveViewer(null)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения доступа')
    } finally {
      setSavingAccess(false)
    }
  }

  const countGranted = (userId: number) => accessMap[userId]?.length ?? 0

  const openUserEditor = (user: PanelUser) => {
    setActiveEditor(user)
    setDraftTelegramId(user.telegram_id || '')
    setDraftConfigQuota(
      user.config_quota != null && user.config_quota > 0 ? String(user.config_quota) : '',
    )
  }

  const saveUserTelegramId = async () => {
    if (!activeEditor) return
    setSavingUser(true)
    try {
      const payload: Record<string, unknown> = { telegram_id: draftTelegramId.trim() }
      if (activeEditor.role === 'user') {
        const raw = draftConfigQuota.trim()
        payload.config_quota = raw === '' ? 0 : Number.parseInt(raw, 10)
        if (raw !== '' && (!Number.isFinite(payload.config_quota as number) || (payload.config_quota as number) < 0)) {
          notifyError('Квота: целое число ≥ 0 (0 = без лимита по умолчанию)')
          return
        }
      }
      const updated = await updateUser(activeEditor.id, payload)
      setUsersList((prev) => prev.map((item) => (item.id === updated.id ? updated : item)))
      success(`Telegram ID для «${updated.username}» сохранён`)
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
              icon={Eye}
              label="Только просмотр"
              value={String(stats.viewers)}
              tone={stats.viewers > 0 ? 'default' : 'muted'}
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
                    onEdit={() => openUserEditor(u)}
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
                                onClick={() => openUserEditor(u)}
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

        {(viewerUsers.length > 0 || !configsLoading) && (
          <SectionHeading
            title="Доступ к конфигам"
            description="Ограничение видимости VPN-клиентов для роли «Только просмотр»"
          />
        )}

        <Card className="overflow-hidden shadow-sm md:col-span-2">
          <div className="h-1 bg-gradient-to-r from-amber-500/70 to-amber-500/15" />
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Eye size={18} />
              Права просмотра
            </CardTitle>
            <CardDescription>
              Укажите, какие VPN-клиенты может видеть пользователь с ролью «Только просмотр»
            </CardDescription>
          </CardHeader>
          <CardContent>
            {configsLoading ? (
              <Spinner label="Загрузка конфигов..." className="py-8" />
            ) : viewerUsers.length === 0 ? (
              <EmptyState
                icon={Eye}
                title="Нет пользователей с режимом «Только просмотр»"
                description="Создайте пользователя с этой ролью, чтобы ограничить доступ только к выбранным конфигам"
                className="py-8"
              />
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {viewerUsers.map((vu) => {
                  const granted = countGranted(vu.id)
                  const total = clientGroups.length
                  const pct = total > 0 ? Math.round((granted / total) * 100) : 0
                  return (
                    <button
                      key={vu.id}
                      type="button"
                      onClick={() => void openViewerDialog(vu)}
                      className="group flex flex-col gap-3 rounded-xl border bg-card/50 p-4 text-left transition-all hover:border-primary/30 hover:bg-muted/30 hover:shadow-sm"
                    >
                      <div className="flex w-full items-center gap-3">
                        <UserAvatar username={vu.username} />
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-medium group-hover:text-primary">{vu.username}</p>
                          <p className="text-xs text-muted-foreground">{ROLE_LABELS.viewer}</p>
                        </div>
                      </div>
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-muted-foreground">Выдано групп</span>
                          <span className="font-medium">
                            {granted} / {total}
                          </span>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                          <div
                            className={cn(
                              'h-full rounded-full transition-all',
                              pct === 100 ? 'bg-primary' : pct > 0 ? 'bg-primary/70' : 'bg-muted-foreground/20',
                            )}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    </button>
                  )
                })}
              </div>
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
        description="Привязка Telegram и лимит VPN-клиентов"
        icon={Users}
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
            <div className="flex items-center gap-3 rounded-xl border bg-muted/20 p-3">
              <UserAvatar username={activeEditor.username} />
              <div>
                <p className="font-medium">{activeEditor.username}</p>
                <RoleBadge role={activeEditor.role} />
              </div>
            </div>
          )}
          <div className="space-y-2 rounded-xl border bg-muted/20 p-4">
            <Label htmlFor="editTelegramId">Telegram ID</Label>
            <Input
              id="editTelegramId"
              value={draftTelegramId}
              onChange={(e) => setDraftTelegramId(e.target.value)}
              placeholder="123456789"
              className="font-mono"
            />
            <p className="text-xs text-muted-foreground">
              Оставьте пустым, чтобы снять привязку. Один ID нельзя назначить двум пользователям.
            </p>
          </div>
          {activeEditor?.role === 'user' && (
            <div className="space-y-2 rounded-xl border bg-muted/20 p-4">
              <Label htmlFor="editConfigQuota">Квота конфигов</Label>
              <Input
                id="editConfigQuota"
                type="number"
                min={0}
                max={1000}
                value={draftConfigQuota}
                onChange={(e) => setDraftConfigQuota(e.target.value)}
                placeholder="по умолчанию"
              />
              <p className="text-xs text-muted-foreground">
                Максимум VPN-клиентов, которых может создать этот пользователь. Пусто — общий лимит панели.
              </p>
            </div>
          )}
        </div>
      </AppDialog>

      <AppDialog
        open={activeViewer !== null}
        onOpenChange={(open) => {
          if (!open && !savingAccess) setActiveViewer(null)
        }}
        title={activeViewer ? `Доступ: ${activeViewer.username}` : 'Доступ к конфигам'}
        description="Отметьте клиентов, которых этот пользователь может просматривать и скачивать"
        icon={Eye}
        size="lg"
        className="max-w-2xl"
        footer={
          <>
            <Button variant="outline" onClick={() => setActiveViewer(null)} disabled={savingAccess}>
              Отмена
            </Button>
            <Button onClick={() => void saveViewerAccess()} disabled={savingAccess || accessLoading}>
              <Save size={16} />
              {savingAccess ? 'Сохранение...' : 'Сохранить'}
            </Button>
          </>
        }
      >
        {accessLoading ? (
          <Spinner label="Загрузка доступа..." className="py-8" />
        ) : (
          <div className="space-y-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Поиск по имени клиента..."
                className="pl-9"
              />
            </div>
            {clientGroups.length === 0 ? (
              <p className="text-sm text-muted-foreground">Конфиги не найдены на активном узле</p>
            ) : filteredGroups.length === 0 ? (
              <p className="text-sm text-muted-foreground">Ничего не найдено</p>
            ) : (
              <div className="max-h-80 space-y-1.5 overflow-y-auto rounded-xl border bg-muted/20 p-2">
                {filteredGroups.map((name) => {
                  const checked = draftGroups.includes(name)
                  const types = configs
                    .filter((c) => c.client_name === name)
                    .map((c) => c.vpn_type)
                    .filter((t, i, arr) => arr.indexOf(t) === i)
                  return (
                    <label
                      key={name}
                      className={cn(
                        'flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors',
                        checked ? 'border-primary/30 bg-primary/5' : 'border-transparent bg-card/50 hover:bg-muted/50',
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => toggleGroup(name, e.target.checked)}
                        className="h-4 w-4 rounded border-input"
                      />
                      <span className="min-w-0 flex-1 font-medium">{name}</span>
                      <span className="flex shrink-0 gap-1">
                        {types.map((t) => (
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
            <div className="flex items-center justify-between rounded-lg border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
              <span>Выбрано групп</span>
              <span className="font-medium text-foreground">
                {draftGroups.length} из {clientGroups.length}
              </span>
            </div>
          </div>
        )}
      </AppDialog>
    </div>
  )
}
