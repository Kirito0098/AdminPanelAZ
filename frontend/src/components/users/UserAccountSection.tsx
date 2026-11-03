import { useState } from 'react'
import { Copy, LogIn, Phone, StickyNote, Trash2 } from 'lucide-react'
import { createUserTelegramLinkCode } from '@/api/users'
import { useNotifications } from '@/context/NotificationContext'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import type { UserProvisionSummary, UserUpdatePayload } from '@/types'
import UserSection from './UserSection'

interface UserAccountSectionProps {
  user: UserProvisionSummary
  onSave: (id: number, data: Partial<UserUpdatePayload>, message?: string) => void
  onDelete: (user: UserProvisionSummary) => void
}

export default function UserAccountSection({ user, onSave, onDelete }: UserAccountSectionProps) {
  const { error: notifyError, success } = useNotifications()
  const [panelLogin, setPanelLogin] = useState(Boolean(user.panel_login_enabled))
  const [password, setPassword] = useState('')
  const [linkCode, setLinkCode] = useState<string | null>(null)
  const [linkCodeLoading, setLinkCodeLoading] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [note, setNote] = useState(user.note ?? '')

  const hasChanges = panelLogin !== Boolean(user.panel_login_enabled) || password.trim().length > 0

  const handleSave = () => {
    const updates: Partial<UserUpdatePayload> = {}
    if (panelLogin !== Boolean(user.panel_login_enabled)) updates.panel_login_enabled = panelLogin
    if (password.trim().length > 0) updates.password = password.trim()
    if (Object.keys(updates).length === 0) return
    onSave(user.id, updates)
    if (updates.password) setPassword('')
  }

  const handleCreateLinkCode = async () => {
    setLinkCodeLoading(true)
    try {
      const data = await createUserTelegramLinkCode(user.id)
      setLinkCode(data.code)
      success(
        `Команда привязки: /link ${data.code} (действует ${Math.round(data.expires_in_seconds / 60)} мин.)`,
      )
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Ошибка создания кода')
    } finally {
      setLinkCodeLoading(false)
    }
  }

  const handleCopyLinkCode = async () => {
    if (!linkCode) return
    try {
      await navigator.clipboard.writeText(`/link ${linkCode}`)
      success('Команда /link скопирована')
    } catch {
      notifyError('Не удалось скопировать код')
    }
  }

  const handleDelete = () => {
    onDelete(user)
    setDeleteOpen(false)
  }

  const handleSaveNote = () => {
    onSave(user.id, { note: note.trim() ? note.trim() : null }, 'Заметка сохранена')
  }

  return (
    <div className="space-y-3">
      <UserSection
        icon={LogIn}
        title="Вход в панель"
        description="Доступ абонента к админ-панели — не влияет на конфиги и Telegram."
      >
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3 rounded-lg border bg-muted/20 px-3 py-2.5">
            <div className="space-y-0.5">
              <Label htmlFor="accountPanelLogin">Разрешить вход в панель</Label>
              <p className="text-xs text-muted-foreground">
                Выкл. — абонент не сможет войти под своим логином
              </p>
            </div>
            <Switch id="accountPanelLogin" checked={panelLogin} onCheckedChange={setPanelLogin} />
          </div>
          <div className="space-y-1.5 rounded-lg border bg-muted/20 px-3 py-2.5">
            <Label htmlFor="accountPassword">Сброс пароля</Label>
            <Input
              id="accountPassword"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Новый пароль (минимум 4 символа)"
              className="h-9"
            />
            <p className="text-xs text-muted-foreground">
              Оставьте пустым, чтобы не менять пароль
            </p>
          </div>
          <Button type="button" onClick={handleSave} disabled={!hasChanges} title={!hasChanges ? 'Нет изменений' : undefined}>
            Сохранить
          </Button>
        </div>
      </UserSection>

      <UserSection
        icon={StickyNote}
        title="Заметка"
        description="Внутренняя заметка администратора — видна только в панели."
      >
        <div className="space-y-2">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={3}
            placeholder="Например: оплатил до 1 декабря, VIP…"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          />
          <Button type="button" onClick={handleSaveNote}>
            Сохранить заметку
          </Button>
        </div>
      </UserSection>

      <UserSection
        icon={Phone}
        title="Привязка Telegram"
        description={
          user.telegram_id
            ? 'Telegram привязан. Код для перепривязки — команда /link в боте, 10 минут.'
            : 'Код для команды /link в боте. Действует 10 минут.'
        }
      >
        <div className="space-y-3">
          {user.telegram_id ? (
            <div className="rounded-lg border bg-muted/20 px-3 py-2.5">
              <p className="text-xs text-muted-foreground">Привязанный Telegram ID</p>
              <p className="font-mono text-sm font-medium">{user.telegram_id}</p>
            </div>
          ) : null}
          <Button
            type="button"
            onClick={handleCreateLinkCode}
            disabled={linkCodeLoading}
            className="w-full sm:w-auto"
          >
            {linkCodeLoading ? (
              'Создание…'
            ) : (
              <>
                <Phone size={15} /> {user.telegram_id ? 'Перепривязать' : 'Получить код'}
              </>
            )}
          </Button>
          {linkCode && (
            <div className="flex items-center justify-between gap-2 rounded-lg border bg-muted/20 px-3 py-2.5">
              <span className="font-mono text-sm font-medium">/link {linkCode}</span>
              <div className="flex items-center gap-1">
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8"
                  onClick={() => void handleCopyLinkCode()}
                  aria-label="Скопировать команду привязки"
                  title="Скопировать"
                >
                  <Copy size={14} />
                </Button>
                <Button type="button" size="sm" variant="outline" onClick={() => setLinkCode(null)}>
                  Скрыть
                </Button>
              </div>
            </div>
          )}
        </div>
      </UserSection>

      <UserSection
        icon={Trash2}
        tone="danger"
        title="Удаление аккаунта"
        description="Абонент и все его конфиги будут удалены без возможности восстановления."
      >
        <Button
          type="button"
          variant="destructive"
          onClick={() => setDeleteOpen(true)}
          className="w-full sm:w-auto"
        >
          <Trash2 size={15} />
          Удалить абонента
        </Button>
      </UserSection>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Удалить пользователя?"
        description={
          <>
            Аккаунт «<strong>{user.username}</strong>» будет удалён без возможности восстановления.
          </>
        }
        confirmLabel="Удалить"
        destructive
        onConfirm={handleDelete}
      />
    </div>
  )
}
