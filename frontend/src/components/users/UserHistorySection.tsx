import { useEffect, useState } from 'react'
import { History } from 'lucide-react'
import { getUserHistory } from '@/api/users'
import { useNotifications } from '@/context/NotificationContext'
import Spinner from '@/components/ui/Spinner'
import { formatDateTime } from '@/lib/datetime'
import type { UserHistoryEntry } from '@/types'
import UserSection from './UserSection'

const ACTION_LABELS: Record<string, string> = {
  user_suspend: 'Приостановлен',
  user_resume: 'Возобновлён',
  user_extend: 'Продлён',
  user_traffic_counter_reset: 'Сброс счётчика трафика',
  user_delete: 'Удалён',
  user_update: 'Изменён',
  user_grace_cleanup: 'Очистка после grace',
  user_provision_update: 'Изменён план',
}

function actionLabel(action: string): string {
  if (action.startsWith('user_bulk_')) return 'Массовая операция'
  return ACTION_LABELS[action] ?? action
}

interface UserHistorySectionProps {
  userId: number
}

export default function UserHistorySection({ userId }: UserHistorySectionProps) {
  const { error: notifyError } = useNotifications()
  const [rows, setRows] = useState<UserHistoryEntry[] | null>(null)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const data = await getUserHistory(userId, 100)
        if (!cancelled) setRows(data)
      } catch (err) {
        if (!cancelled) {
          notifyError(err instanceof Error ? err.message : 'Не удалось загрузить историю')
          setRows([])
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [userId, notifyError])

  return (
    <UserSection
      icon={History}
      title="История действий"
      description="Действия администраторов по абоненту."
    >
      {rows === null ? (
        <Spinner label="Загрузка истории…" className="py-6" />
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">Действий пока не было</p>
      ) : (
        <ul className="space-y-1.5">
          {rows.map((row) => (
            <li
              key={row.id}
              className="flex flex-wrap items-baseline gap-x-2 rounded-lg border bg-muted/20 px-3 py-2 text-sm"
            >
              <span className="font-medium">{actionLabel(row.action)}</span>
              <span className="text-xs text-muted-foreground">{row.actor_username ?? '—'}</span>
              <span className="ml-auto text-xs text-muted-foreground">
                {formatDateTime(row.created_at)}
              </span>
              {row.details ? (
                <span className="basis-full text-[11px] text-muted-foreground">{row.details}</span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </UserSection>
  )
}
