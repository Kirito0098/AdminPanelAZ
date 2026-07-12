import { Link2, Unlink, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ROLE_LABELS } from '@/components/settings/settingsLabels'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import type { User } from '@/types'

interface TelegramLinkedAccountsPanelProps {
  accounts: User[]
  unlinkingUserId: number | null
  onUnlink: (user: User) => void | Promise<void>
}

export default function TelegramLinkedAccountsPanel({
  accounts,
  unlinkingUserId,
  onUnlink,
}: TelegramLinkedAccountsPanelProps) {
  const { confirm, dialogProps } = useConfirmDialog()

  const handleUnlink = (user: User) => {
    confirm({
      title: 'Отвязать Telegram?',
      description: (
        <>
          Пользователь <strong>{user.username}</strong> (ID <code>{user.telegram_id}</code>) больше не сможет
          использовать команды бота и Mini App до новой привязки через <code>/link</code>.
        </>
      ),
      confirmLabel: 'Отвязать',
      destructive: true,
      onConfirm: () => void onUnlink(user),
    })
  }

  return (
    <>
      <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Users size={16} className="text-muted-foreground" />
              <p className="text-sm font-medium">Привязанные аккаунты</p>
            </div>
            <p className="text-xs text-muted-foreground">
              Пользователи панели, у которых указан Telegram ID — через бота они получают команды и конфиги.
            </p>
          </div>
          <Badge variant="outline">{accounts.length}</Badge>
        </div>

        {accounts.length === 0 ? (
          <SettingsAlert variant="info" title="Пока никто не привязан">
            Получите код ниже (или в <Link to="/settings/personal" className="font-medium text-primary underline-offset-4 hover:underline">Мой профиль</Link>) и отправьте боту <code>/link &lt;код&gt;</code>, либо укажите Telegram ID в{' '}
            <Link to="/settings/users" className="font-medium text-primary underline-offset-4 hover:underline">
              Настройки → Пользователи
            </Link>
            .
          </SettingsAlert>
        ) : (
          <div className="overflow-hidden rounded-lg border bg-background/50">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                  <th className="px-3 py-2 font-medium">Пользователь</th>
                  <th className="hidden px-3 py-2 font-medium sm:table-cell">Роль</th>
                  <th className="px-3 py-2 font-medium">Telegram ID</th>
                  <th className="px-3 py-2 font-medium text-right">Действие</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((user) => (
                  <tr key={user.id} className="border-b last:border-b-0">
                    <td className="px-3 py-2.5 align-middle">
                      <p className="font-medium">{user.username}</p>
                      <p className="text-xs text-muted-foreground sm:hidden">{ROLE_LABELS[user.role]}</p>
                    </td>
                    <td className="hidden px-3 py-2.5 align-middle sm:table-cell">
                      <Badge variant="secondary" className="text-[10px]">
                        {ROLE_LABELS[user.role]}
                      </Badge>
                    </td>
                    <td className="px-3 py-2.5 align-middle">
                      <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{user.telegram_id}</code>
                    </td>
                    <td className="px-3 py-2.5 align-middle text-right">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-8 text-destructive hover:text-destructive"
                        disabled={unlinkingUserId === user.id}
                        onClick={() => handleUnlink(user)}
                      >
                        <Unlink size={14} className="mr-1.5" />
                        {unlinkingUserId === user.id ? 'Отвязка...' : 'Отвязать'}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {accounts.length > 0 && (
          <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
            <Link2 size={14} className="mt-0.5 shrink-0" />
            Отвязка не удаляет пользователя панели — только связь с Telegram. Повторная привязка через{' '}
            <code className="rounded bg-muted px-1">/link</code>.
          </p>
        )}
      </div>
      <ConfirmDialogHost dialogProps={dialogProps} />
    </>
  )
}
