import { FormEvent, useEffect, useMemo, useState } from 'react'
import { Eye, Save, Search, Trash2, UserPlus, Users } from 'lucide-react'
import { ApiError, getConfigs, getViewerAccess, setViewerAccess } from '@/api/client'
import AppDialog from '@/components/shared/AppDialog'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useNotifications } from '@/context/NotificationContext'
import type { User, UserRole, VpnConfig } from '@/types'

const roleLabels: Record<UserRole, string> = {
  admin: 'Администратор',
  user: 'Пользователь',
  viewer: 'Просмотр',
}

interface UsersTabProps {
  users: User[]
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
  const [activeViewer, setActiveViewer] = useState<User | null>(null)
  const [draftGroups, setDraftGroups] = useState<string[]>([])
  const [accessLoading, setAccessLoading] = useState(false)
  const [savingAccess, setSavingAccess] = useState(false)
  const [search, setSearch] = useState('')

  const viewerUsers = useMemo(() => users.filter((u) => u.role === 'viewer'), [users])

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

  const openViewerDialog = async (user: User) => {
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

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <UserPlus size={18} />
            Новый пользователь
          </CardTitle>
          <CardDescription>Создание учётной записи с выбранной ролью</CardDescription>
        </CardHeader>
        <CardContent>
          <form noValidate onSubmit={onCreateUser} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-2">
              <Label htmlFor="newUsername">Логин</Label>
              <Input
                id="newUsername"
                value={newUsername}
                onChange={(e) => onNewUsernameChange(e.target.value)}
                placeholder="username"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="newPassword">Пароль</Label>
              <Input
                id="newPassword"
                type="password"
                value={newPassword}
                onChange={(e) => onNewPasswordChange(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>Роль</Label>
              <Select value={newRole} onValueChange={(v) => onNewRoleChange(v as UserRole)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">Пользователь</SelectItem>
                  <SelectItem value="viewer">Просмотр (viewer)</SelectItem>
                  <SelectItem value="admin">Администратор</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end">
              <Button type="submit">
                <UserPlus size={16} />
                Добавить
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Users size={18} />
            Список пользователей
          </CardTitle>
          <CardDescription>
            {users.length > 0 ? `${users.length} учётн${users.length === 1 ? 'ая запись' : 'ых записей'}` : 'Пользователи не найдены'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {users.length === 0 ? (
            <EmptyState
              icon={Users}
              title="Нет пользователей"
              description="Создайте первую учётную запись с помощью формы выше"
              className="py-8"
            />
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Логин</TableHead>
                    <TableHead>Роль</TableHead>
                    <TableHead>Статус</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {users.map((u) => (
                    <TableRow key={u.id}>
                      <TableCell className="text-muted-foreground">{u.id}</TableCell>
                      <TableCell className="font-medium">{u.username}</TableCell>
                      <TableCell>
                        <Badge variant={u.role === 'admin' ? 'default' : 'secondary'}>
                          {roleLabels[u.role] ?? u.role}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={u.is_active ? 'success' : 'destructive'}>
                          {u.is_active ? 'Активен' : 'Отключён'}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {u.id !== currentUserId && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="border-destructive/30 text-destructive hover:bg-destructive/10"
                            onClick={() => onDeleteUser(u.id, u.username)}
                          >
                            <Trash2 size={14} />
                            Удалить
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Eye size={18} />
            Доступ к конфигам (viewer)
          </CardTitle>
          <CardDescription>
            Назначение групп конфигов для пользователей с ролью «Просмотр»
          </CardDescription>
        </CardHeader>
        <CardContent>
          {configsLoading ? (
            <Spinner label="Загрузка конфигов..." className="py-8" />
          ) : viewerUsers.length === 0 ? (
            <EmptyState
              icon={Eye}
              title="Нет viewer-пользователей"
              description="Создайте пользователя с ролью «Просмотр», чтобы назначить доступ к конфигам"
              className="py-8"
            />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {viewerUsers.map((vu) => (
                <button
                  key={vu.id}
                  type="button"
                  onClick={() => void openViewerDialog(vu)}
                  className="flex flex-col items-start gap-2 rounded-lg border bg-card p-4 text-left transition-colors hover:bg-muted/50"
                >
                  <div className="flex w-full items-center justify-between gap-2">
                    <span className="font-medium">{vu.username}</span>
                    <Badge variant="secondary">{roleLabels.viewer}</Badge>
                  </div>
                  <span className="text-sm text-muted-foreground">
                    Выдано групп: {countGranted(vu.id)} из {clientGroups.length}
                  </span>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <AppDialog
        open={activeViewer !== null}
        onOpenChange={(open) => {
          if (!open && !savingAccess) setActiveViewer(null)
        }}
        title={activeViewer ? `Доступ: ${activeViewer.username}` : 'Доступ viewer'}
        description="Выберите клиентские группы, которые viewer может просматривать и скачивать"
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
              <div className="max-h-80 space-y-2 overflow-y-auto rounded-md border p-3">
                {filteredGroups.map((name) => {
                  const checked = draftGroups.includes(name)
                  const types = configs
                    .filter((c) => c.client_name === name)
                    .map((c) => c.vpn_type)
                    .filter((t, i, arr) => arr.indexOf(t) === i)
                  return (
                    <label
                      key={name}
                      className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 hover:bg-muted/50"
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
                          <Badge key={t} variant="outline" className="text-xs">
                            {t}
                          </Badge>
                        ))}
                      </span>
                    </label>
                  )
                })}
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              Выбрано: {draftGroups.length} из {clientGroups.length}
            </p>
          </div>
        )}
      </AppDialog>
    </div>
  )
}
