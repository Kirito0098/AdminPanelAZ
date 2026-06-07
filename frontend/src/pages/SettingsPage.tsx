import { FormEvent, useEffect, useState } from 'react'
import {
  KeyRound,
  Moon,
  Palette,
  Settings,
  Shield,
  Sun,
  Trash2,
  UserPlus,
  Users,
} from 'lucide-react'
import { ApiError, changePassword, createUser, deleteUser, getSettings, getUsers, updateSettings } from '@/api/client'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { NodeBadge } from '@/components/NodeSelector'
import { useAuth } from '@/context/AuthContext'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { useTheme } from '@/context/ThemeContext'
import BackupTab from '@/components/settings/BackupTab'
import MaintenanceTab from '@/components/settings/MaintenanceTab'
import TelegramTab from '@/components/settings/TelegramTab'
import SecurityTab from '@/components/settings/SecurityTab'
import TestsTab from '@/components/settings/TestsTab'
import UpdatesTab from '@/components/settings/UpdatesTab'
import type { AppSettings, User, UserRole } from '@/types'

export default function SettingsPage() {
  const { user } = useAuth()
  const { activeNode } = useNode()
  const { theme, setTheme } = useTheme()
  const { success, error: notifyError } = useNotifications()
  const { startGlobal, doneGlobal, inline, withInline } = useProgress()
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [users, setUsers] = useState<User[]>([])
  const [includeHosts, setIncludeHosts] = useState('')
  const [excludeHosts, setExcludeHosts] = useState('')
  const [includeIps, setIncludeIps] = useState('')
  const [excludeIps, setExcludeIps] = useState('')
  const [allowIps, setAllowIps] = useState('')
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newRole, setNewRole] = useState<UserRole>('user')
  const [currentPwd, setCurrentPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [savingAntizapret, setSavingAntizapret] = useState(false)

  const load = async () => {
    startGlobal()
    try {
      const s = await getSettings()
      setSettings(s)
      setIncludeHosts(s.include_hosts)
      setExcludeHosts(s.exclude_hosts)
      setIncludeIps(s.include_ips)
      setExcludeIps(s.exclude_ips)
      setAllowIps(s.allow_ips)
      if (user?.role === 'admin') {
        setUsers(await getUsers())
      }
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки настроек')
    } finally {
      doneGlobal()
    }
  }

  useEffect(() => {
    load()
  }, [user?.role])

  const saveAntizapret = async (e: FormEvent) => {
    e.preventDefault()
    setSavingAntizapret(true)
    try {
      await withInline(async () => {
        await updateSettings({
          include_hosts: includeHosts,
          exclude_hosts: excludeHosts,
          include_ips: includeIps,
          exclude_ips: excludeIps,
          allow_ips: allowIps,
        })
      }, 'Применение настроек (doall.sh)...')
      success('Списки AntiZapret обновлены и применены')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSavingAntizapret(false)
    }
  }

  const handleCreateUser = async (e: FormEvent) => {
    e.preventDefault()
    const createdName = newUsername
    try {
      await createUser({ username: createdName, password: newPassword, role: newRole })
      setNewUsername('')
      setNewPassword('')
      setUsers(await getUsers())
      success(`Пользователь «${createdName}» создан`)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка создания пользователя')
    }
  }

  const handleDeleteUser = async (id: number, name: string) => {
    if (!confirm(`Удалить пользователя "${name}"?`)) return
    try {
      await deleteUser(id)
      setUsers(await getUsers())
      success(`Пользователь «${name}» удалён`)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка удаления')
    }
  }

  const handleChangePassword = async (e: FormEvent) => {
    e.preventDefault()
    try {
      await changePassword(currentPwd, newPwd)
      setCurrentPwd('')
      setNewPwd('')
      success('Пароль изменён')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка смены пароля')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Settings size={22} />
        </div>
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-2xl font-bold tracking-tight">Настройки</h2>
            <NodeBadge name={activeNode?.name ?? settings?.node_name} status={activeNode?.status} />
          </div>
          <p className="text-sm text-muted-foreground">Тема, безопасность и конфигурация AntiZapret</p>
        </div>
      </div>

      <InlineProgressBar active={inline.active} label={inline.label} />

      <Tabs defaultValue="personal" className="space-y-4">
        <TabsList>
          <TabsTrigger value="personal">Личные</TabsTrigger>
          {user?.role === 'admin' && (
            <>
              <TabsTrigger value="admin">Списки</TabsTrigger>
              <TabsTrigger value="maintenance">Обслуживание</TabsTrigger>
              <TabsTrigger value="backup">Бэкапы</TabsTrigger>
              <TabsTrigger value="telegram">Telegram</TabsTrigger>
              <TabsTrigger value="security">Безопасность</TabsTrigger>
              <TabsTrigger value="updates">Обновления</TabsTrigger>
              <TabsTrigger value="tests">Тесты</TabsTrigger>
              <TabsTrigger value="users">Пользователи</TabsTrigger>
            </>
          )}
        </TabsList>

        <TabsContent value="personal" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Palette size={18} />
                Внешний вид
              </CardTitle>
              <CardDescription>Выберите тему интерфейса панели</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2">
                <Button variant={theme === 'light' ? 'default' : 'secondary'} onClick={() => setTheme('light')}>
                  <Sun size={16} />
                  Светлая
                </Button>
                <Button variant={theme === 'dark' ? 'default' : 'secondary'} onClick={() => setTheme('dark')}>
                  <Moon size={16} />
                  Тёмная
                </Button>
              </div>
              {settings && (
                <p className="text-sm text-muted-foreground">
                  Путь AntiZapret:{' '}
                  <code className="mono rounded bg-muted px-1.5 py-0.5 text-xs">{settings.antizapret_path}</code>
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <KeyRound size={18} />
                Смена пароля
              </CardTitle>
              <CardDescription>Обновите пароль для вашей учётной записи</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleChangePassword} className="grid max-w-md gap-4">
                <div className="space-y-2">
                  <Label htmlFor="currentPwd">Текущий пароль</Label>
                  <Input
                    id="currentPwd"
                    type="password"
                    value={currentPwd}
                    onChange={(e) => setCurrentPwd(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="newPwd">Новый пароль</Label>
                  <Input
                    id="newPwd"
                    type="password"
                    value={newPwd}
                    onChange={(e) => setNewPwd(e.target.value)}
                    required
                    minLength={4}
                  />
                </div>
                <Button type="submit" className="w-fit">
                  Сохранить пароль
                </Button>
              </form>
            </CardContent>
          </Card>
        </TabsContent>

        {user?.role === 'admin' && (
          <TabsContent value="admin" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Shield size={18} />
                  Списки AntiZapret
                </CardTitle>
                <CardDescription>Редактирование доменов и IP-адресов для обхода блокировок</CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={saveAntizapret} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="includeHosts">Включить домены (include-hosts.txt)</Label>
                    <Textarea id="includeHosts" rows={6} value={includeHosts} onChange={(e) => setIncludeHosts(e.target.value)} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="excludeHosts">Исключить домены (exclude-hosts.txt)</Label>
                    <Textarea id="excludeHosts" rows={6} value={excludeHosts} onChange={(e) => setExcludeHosts(e.target.value)} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="includeIps">Включить IP (include-ips.txt)</Label>
                    <Textarea id="includeIps" rows={4} value={includeIps} onChange={(e) => setIncludeIps(e.target.value)} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="excludeIps">Исключить IP (exclude-ips.txt)</Label>
                    <Textarea id="excludeIps" rows={4} value={excludeIps} onChange={(e) => setExcludeIps(e.target.value)} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="allowIps">Разрешённые IP (allow-ips.txt)</Label>
                    <Textarea id="allowIps" rows={3} value={allowIps} onChange={(e) => setAllowIps(e.target.value)} />
                  </div>
                  <Button type="submit" disabled={savingAntizapret}>
                    {savingAntizapret ? 'Применение...' : 'Сохранить и применить (doall.sh)'}
                  </Button>
                </form>
              </CardContent>
            </Card>

          </TabsContent>
        )}

        {user?.role === 'admin' && (
          <TabsContent value="maintenance">
            <MaintenanceTab />
          </TabsContent>
        )}

        {user?.role === 'admin' && (
          <TabsContent value="backup">
            <BackupTab />
          </TabsContent>
        )}

        {user?.role === 'admin' && (
          <TabsContent value="telegram">
            <TelegramTab />
          </TabsContent>
        )}

        {user?.role === 'admin' && (
          <TabsContent value="security">
            <SecurityTab />
          </TabsContent>
        )}

        {user?.role === 'admin' && (
          <TabsContent value="updates">
            <UpdatesTab />
          </TabsContent>
        )}

        {user?.role === 'admin' && (
          <TabsContent value="tests">
            <TestsTab />
          </TabsContent>
        )}

        {user?.role === 'admin' && (
          <TabsContent value="users" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Users size={18} />
                  Управление пользователями
                </CardTitle>
                <CardDescription>Добавление и удаление учётных записей</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <form onSubmit={handleCreateUser} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="space-y-2">
                    <Label htmlFor="newUsername">Логин</Label>
                    <Input
                      id="newUsername"
                      value={newUsername}
                      onChange={(e) => setNewUsername(e.target.value)}
                      required
                      placeholder="username"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="newPassword">Пароль</Label>
                    <Input
                      id="newPassword"
                      type="password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Роль</Label>
                    <Select value={newRole} onValueChange={(v) => setNewRole(v as UserRole)}>
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
                          <TableCell>{u.id}</TableCell>
                          <TableCell className="font-medium">{u.username}</TableCell>
                          <TableCell>
                            <Badge variant={u.role === 'admin' ? 'default' : 'secondary'}>
                              {u.role === 'admin' ? 'Администратор' : 'Пользователь'}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge variant={u.is_active ? 'success' : 'destructive'}>
                              {u.is_active ? 'Активен' : 'Отключён'}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            {u.id !== user?.id && (
                              <Button
                                variant="outline"
                                size="sm"
                                className="border-destructive/30 text-destructive hover:bg-destructive/10"
                                onClick={() => handleDeleteUser(u.id, u.username)}
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
              </CardContent>
            </Card>
          </TabsContent>
        )}
      </Tabs>
    </div>
  )
}
