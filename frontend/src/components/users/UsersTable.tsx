import {
  ExternalLink,
  KeyRound,
  MoreHorizontal,
  PauseCircle,
  Play,
  RotateCcw,
  Trash2,
} from 'lucide-react'
import type { User } from '@/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { formatRelative } from '@/lib/datetime'
import { formatBytes } from '@/lib/trafficFormat'
import { accessParts, resolveCardState } from '@/lib/userState'
import type { UsersSortDir, UsersSortKey } from '@/lib/usersListPrefs'
import { cn } from '@/lib/utils'

const COLUMNS: { key: UsersSortKey | null; label: string; className?: string }[] = [
  { key: 'username', label: 'Логин' },
  { key: null, label: 'Статус' },
  { key: 'access_until', label: 'Срок' },
  { key: 'traffic', label: 'Трафик' },
  { key: 'last_seen', label: 'Активность' },
  { key: null, label: 'Узлы' },
  { key: null, label: 'Действия', className: 'text-right' },
]

export interface UsersTableProps {
  users: User[]
  selectedIds: number[]
  onSelectChange: (id: number, checked: boolean) => void
  onOpen: (user: User) => void
  onExtend: (user: User, days: number) => void
  onResetTraffic: (user: User) => void
  onSuspend: (user: User) => void
  onResume: (user: User) => void
  onDelete: (user: User) => void
  onRetryDelete: (user: User) => void
  onCreateKey?: (user: User) => void
  sortKey: UsersSortKey
  sortDir: UsersSortDir
  onSortChange: (key: UsersSortKey) => void
  actionBusyId: number | null
}

export default function UsersTable({
  users,
  selectedIds,
  onSelectChange,
  onOpen,
  onExtend,
  onResetTraffic,
  onSuspend,
  onResume,
  onDelete,
  onRetryDelete,
  onCreateKey,
  sortKey,
  sortDir,
  onSortChange,
  actionBusyId,
}: UsersTableProps) {
  if (users.length === 0) {
    return <div className="py-10 text-center text-sm text-muted-foreground">Нет абонентов</div>
  }
  return (
    <div className="overflow-x-auto rounded-xl border">
      <table className="w-full min-w-[960px] border-collapse text-sm">
        <thead className="sticky top-0 z-10 bg-muted/80 backdrop-blur">
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th className="w-10 px-3 py-2" aria-label="Выбор" />
            {COLUMNS.map((col) => (
              <th key={col.label} className={cn('px-3 py-2 font-medium', col.className)}>
                {col.key ? (
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 hover:text-foreground"
                    onClick={() => onSortChange(col.key as UsersSortKey)}
                  >
                    {col.label}
                    {sortKey === col.key ? <span aria-hidden>{sortDir === 'asc' ? '↑' : '↓'}</span> : null}
                  </button>
                ) : (
                  col.label
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {users.map((user) => {
            const state = resolveCardState(user)
            const access = accessParts(user)
            const limit = user.traffic_limit_bytes ?? null
            const consumed = user.traffic_consumed_bytes ?? 0
            const selected = selectedIds.includes(user.id)
            const busy = actionBusyId === user.id
            return (
              <tr
                key={user.id}
                className={cn('border-b last:border-0 hover:bg-muted/40', selected && 'bg-primary/5')}
              >
                <td className="px-3 py-2">
                  <Checkbox
                    checked={selected}
                    onCheckedChange={(checked) => onSelectChange(user.id, checked === true)}
                    aria-label={`Выбрать ${user.username}`}
                  />
                </td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{user.username}</span>
                    {user.role === 'admin' ? <Badge variant="secondary">Админ</Badge> : null}
                    {user.online ? (
                      <span className="h-2 w-2 rounded-full bg-emerald-500" title="Онлайн" />
                    ) : null}
                  </div>
                  {user.telegram_id ? (
                    <div className="text-xs text-muted-foreground">TG {user.telegram_id}</div>
                  ) : null}
                </td>
                <td className="px-3 py-2">
                  <Badge variant={state.variant}>{state.label}</Badge>
                </td>
                <td className="whitespace-nowrap px-3 py-2">{access.text}</td>
                <td className="whitespace-nowrap px-3 py-2">
                  {limit && limit > 0 ? `${formatBytes(consumed)} / ${formatBytes(limit)}` : '—'}
                </td>
                <td className="whitespace-nowrap px-3 py-2">
                  {user.online ? (
                    <span className="text-emerald-600 dark:text-emerald-400">онлайн</span>
                  ) : user.last_seen_at ? (
                    formatRelative(user.last_seen_at)
                  ) : (
                    '—'
                  )}
                </td>
                <td className="whitespace-nowrap px-3 py-2">{user.plan_node_ids?.length ?? 0}</td>
                <td className="px-3 py-2 text-right">
                  <div className="flex justify-end gap-1">
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="h-8 gap-1"
                      onClick={() => onOpen(user)}
                      disabled={busy}
                      aria-label={`Открыть ${user.username}`}
                    >
                      <ExternalLink size={14} />
                      Открыть
                    </Button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8"
                          disabled={busy}
                          aria-label={`Действия ${user.username}`}
                        >
                          <MoreHorizontal size={16} />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-52">
                        <DropdownMenuItem onClick={() => onExtend(user, 30)}>+30 дней</DropdownMenuItem>
                        <DropdownMenuItem onClick={() => onExtend(user, 60)}>+60 дней</DropdownMenuItem>
                        {onCreateKey ? (
                          <DropdownMenuItem onClick={() => onCreateKey(user)}>
                            <KeyRound size={14} /> Ключ
                          </DropdownMenuItem>
                        ) : null}
                        {limit && limit > 0 ? (
                          <DropdownMenuItem onClick={() => onResetTraffic(user)}>
                            <RotateCcw size={14} /> Сбросить трафик
                          </DropdownMenuItem>
                        ) : null}
                        <DropdownMenuSeparator />
                        {user.suspended_at ? (
                          <DropdownMenuItem onClick={() => onResume(user)}>
                            <Play size={14} /> Возобновить
                          </DropdownMenuItem>
                        ) : (
                          <DropdownMenuItem onClick={() => onSuspend(user)}>
                            <PauseCircle size={14} /> Приостановить
                          </DropdownMenuItem>
                        )}
                        {user.provision_state === 'pending_deletion' ? (
                          <DropdownMenuItem onClick={() => onRetryDelete(user)}>
                            <RotateCcw size={14} /> Повторить удаление
                          </DropdownMenuItem>
                        ) : (
                          <DropdownMenuItem className="text-destructive" onClick={() => onDelete(user)}>
                            <Trash2 size={14} /> Удалить
                          </DropdownMenuItem>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
