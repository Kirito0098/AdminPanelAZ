import { FormEvent } from 'react'
import { Trash2, UserPlus, Users } from 'lucide-react'
import EmptyState from '@/components/ui/EmptyState'
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
import type { User, UserRole } from '@/types'

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
    </div>
  )
}
