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
  X,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError, updateUser } from '@/api/client'
import AppDialog from '@/components/shared/AppDialog'
import ResponsiveDataView from '@/components/shared/ResponsiveDataView'
import PasswordChangePolicyRow from '@/components/settings/PasswordChangePolicyRow'
import {
  SettingsCard as Card,
  SettingsCardContent as CardContent,
  SettingsCardDescription as CardDescription,
  SettingsCardHeader as CardHeader,
  SettingsCardTitle as CardTitle,
} from '@/components/settings/SettingsCard'
import ToggleRow from '@/components/settings/ToggleRow'
import EmptyState from '@/components/ui/EmptyState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
import { useFeatureModules } from '@/context/FeatureModulesContext'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { SettingsToolbar } from '@/components/settings/SettingsChrome'
import { ROLE_HINTS, ROLE_LABELS } from '@/components/settings/settingsLabels'
import { cn } from '@/lib/utils'
import type { User as PanelUser, UserRole, UserUpdatePayload } from '@/types'

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

/** Панельная учётная запись: админ или аккаунт с включённым входом в панель. */
function isPanelAccount(user: PanelUser) {
  return user.role === 'admin' || Boolean(user.panel_login_enabled)
}

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
  if (user.panel_login_enabled === false) bits.push('Вход в панель выкл.')
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
    <div className="rounded-lg border border-border/70 bg-card px-3 py-3 transition-colors hover:border-primary/20 hover:bg-primary/[0.03]">
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
  const { isEnabled } = useFeatureModules()
  const provisioningOn = isEnabled('user_provisioning')
  const [userQuery, setUserQuery] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [activeEditor, setActiveEditor] = useState<PanelUser | null>(null)
  const [draftRole, setDraftRole] = useState<UserRole>('user')
  const [draftTelegramId, setDraftTelegramId] = useState('')
  const [draftActive, setDraftActive] = useState(true)
  const [draftPanelLogin, setDraftPanelLogin] = useState(true)
  const [draftPassword, setDraftPassword] = useState('')
  const [savingUser, setSavingUser] = useState(false)
  const [usersList, setUsersList] = useState(users)

  useEffect(() => {
    setUsersList(users)
  }, [users])

  const displayedUsers = useMemo(() => usersList.filter(isPanelAccount), [usersList])

  const stats = useMemo(
    () => ({
      total: displayedUsers.length,
      admins: displayedUsers.filter((u) => u.role === 'admin').length,
      regular: displayedUsers.filter((u) => u.role === 'user').length,
      active: displayedUsers.filter((u) => u.is_active).length,
    }),
    [displayedUsers],
  )

  const filteredUsers = useMemo(() => {
    const q = userQuery.trim().toLowerCase()
    if (!q) return displayedUsers
    return displayedUsers.filter((u) => {
      const tg = (u.telegram_id || '').toLowerCase()
      const role = (ROLE_LABELS[u.role] || u.role).toLowerCase()
      return (
        u.username.toLowerCase().includes(q) ||
        tg.includes(q) ||
        role.includes(q) ||
        String(u.id).includes(q)
      )
    })
  }, [displayedUsers, userQuery])

  const openUserEditor = (user: PanelUser) => {
    setActiveEditor(user)
    setDraftRole(user.role)
    setDraftTelegramId(user.telegram_id || '')
    setDraftActive(user.is_active)
    setDraftPanelLogin(user.panel_login_enabled !== false)
    setDraftPassword('')
  }

  const saveUser = async () => {
    if (!activeEditor) return
    const password = draftPassword.trim()
    if (password && password.length < 4) {
      notifyError('Пароль — минимум 4 символа')
      return
    }
    setSavingUser(true)
    try {
      const payload: UserUpdatePayload = {
        role: draftRole,
        telegram_id: draftTelegramId.trim(),
        is_active: draftActive,
        panel_login_enabled: draftPanelLogin,
      }
      if (password) payload.password = password
      const updated = await updateUser(activeEditor.id, payload)
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
      {provisioningOn && (
        <SettingsAlert variant="info">
          Абоненты VPN, их конфиги и квоты — в разделе{' '}
          <Link
            to="/users"
            className="font-medium text-foreground underline underline-offset-4 transition-colors hover:text-primary"
          >
            Абоненты
          </Link>
          .
        </SettingsAlert>
      )}

      {createOpen ? (
        <Card className="border-primary/25 ring-1 ring-primary/10">
          <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
            <div className="flex min-w-0 items-start gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <UserPlus size={16} aria-hidden />
              </span>
              <div className="min-w-0">
                <CardTitle>Новый пользователь</CardTitle>
                <CardDescription className="mt-0.5">
                  Логин, пароль и роль доступа к панели
                </CardDescription>
              </div>
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

      <Card>
        <CardHeader className="gap-3 border-b border-border/70">
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
                  Добавить пользователя
                </Button>
              </>
            }
          />
        </CardHeader>
        <CardContent className="p-0 pt-0">
          {displayedUsers.length === 0 ? (
            <EmptyState
              icon={Users}
              title="Нет учётных записей панели"
              description="Нажмите «Добавить пользователя», чтобы создать администратора или пользователя панели"
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
                  onEdit={() => openUserEditor(u)}
                  onDelete={() => onDeleteUser(u.id, u.username)}
                />
              ))}
              desktop={
                <Table>
                  <TableHeader className="bg-muted/30 [&_tr]:border-border/70">
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="h-9 pl-4 text-[11px] font-medium uppercase tracking-wide">
                        Пользователь
                      </TableHead>
                      <TableHead className="h-9 text-[11px] font-medium uppercase tracking-wide">
                        Статус
                      </TableHead>
                      <TableHead className="h-9 text-[11px] font-medium uppercase tracking-wide">
                        Роль
                      </TableHead>
                      <TableHead className="h-9 text-[11px] font-medium uppercase tracking-wide">
                        Telegram
                      </TableHead>
                      <TableHead className="h-9 pr-4 text-right"> </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredUsers.map((u) => (
                      <TableRow
                        key={u.id}
                        className="group border-border/60 transition-colors hover:bg-muted/40"
                      >
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
                              onClick={() => openUserEditor(u)}
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

      <PasswordChangePolicyRow />

      <AppDialog
        open={activeEditor !== null}
        onOpenChange={(open) => {
          if (!open && !savingUser) setActiveEditor(null)
        }}
        title={activeEditor ? `Пользователь: ${activeEditor.username}` : 'Пользователь'}
        description="Роль, вход в панель и привязка Telegram"
        icon={Users}
        size="xl"
        bodyClassName="px-5 py-4"
        footer={
          <>
            <Button variant="outline" onClick={() => setActiveEditor(null)} disabled={savingUser}>
              Отмена
            </Button>
            <Button onClick={() => void saveUser()} disabled={savingUser}>
              <Save size={16} />
              {savingUser ? 'Сохранение...' : 'Сохранить'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {activeEditor && (
            <div className="flex items-center gap-3 rounded-lg border border-border/70 bg-muted/20 px-3 py-2.5">
              <UserAvatar username={activeEditor.username} />
              <div className="min-w-0">
                <p className="font-medium leading-tight">{activeEditor.username}</p>
                <div className="mt-1">
                  <RoleBadge role={draftRole} />
                </div>
              </div>
            </div>
          )}

          <div className="space-y-2 rounded-lg border border-border/70 bg-muted/20 p-3">
            <Label>Роль</Label>
            <div className="flex flex-wrap gap-2">
              {ROLE_OPTIONS.map(({ id, icon: Icon }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setDraftRole(id)}
                  disabled={savingUser}
                  className={cn(
                    'inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-all',
                    draftRole === id
                      ? 'border-primary/40 bg-primary/10 text-primary ring-1 ring-primary/20'
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

          <div className="space-y-1.5 rounded-lg border border-border/70 bg-muted/20 p-3">
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

          <ToggleRow
            id="editActive"
            label="Активность"
            description="Выкл. — учётная запись отключена, активные сессии завершаются."
            checked={draftActive}
            onCheckedChange={setDraftActive}
          />

          <ToggleRow
            id="editPanelLogin"
            label="Вход в панель"
            description="Выкл. — войти в панель под этим логином нельзя."
            checked={draftPanelLogin}
            onCheckedChange={(next) => {
              setDraftPanelLogin(next)
              if (!next) setDraftPassword('')
            }}
          />

          {activeEditor?.id === currentUserId ? (
            <p className="rounded-lg border border-dashed border-border/70 bg-muted/10 p-3 text-xs text-muted-foreground">
              Свой пароль меняется в «Моём профиле» — с вводом текущего пароля.
            </p>
          ) : draftPanelLogin ? (
            <div className="space-y-1.5 rounded-lg border border-border/70 bg-muted/20 p-3">
              <Label htmlFor="editPassword">Сброс пароля</Label>
              <Input
                id="editPassword"
                type="password"
                value={draftPassword}
                onChange={(e) => setDraftPassword(e.target.value)}
                placeholder="Новый пароль (минимум 4 символа)"
                autoComplete="new-password"
                className="h-9"
              />
              <p className="text-xs text-muted-foreground">
                Оставьте пустым, чтобы не менять пароль.
              </p>
            </div>
          ) : (
            <p className="rounded-lg border border-dashed border-border/70 bg-muted/10 p-3 text-xs text-muted-foreground">
              Вход в панель выключен — пароль не нужен. Включите вход, чтобы задать новый.
            </p>
          )}
        </div>
      </AppDialog>
    </div>
  )
}
