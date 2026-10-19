import { useState } from 'react'
import { Phone, Trash2 } from 'lucide-react'
import { createUserTelegramLinkCode } from '@/api/users'
import { useNotifications } from '@/context/NotificationContext'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import type { UserProvisionSummary, UserUpdatePayload } from '@/types'

interface UserAccountSectionProps {
  user: UserProvisionSummary
  onSave: (id: number, data: Partial<UserUpdatePayload>) => void
  onDelete: (user: UserProvisionSummary) => void
}

export default function UserAccountSection({ user, onSave, onDelete }: UserAccountSectionProps) {
  const { error: notifyError, success } = useNotifications()
  const [panelLogin, setPanelLogin] = useState(Boolean(user.panel_login_enabled))
  const [password, setPassword] = useState('')
  const [linkCode, setLinkCode] = useState<string | null>(null)
  const [linkCodeLoading, setLinkCodeLoading] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)

  const used = user.plan_config_indexes?.length ?? 0
  const limit = user.config_quota ?? null

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
      success(`Код привязки Telegram: ${data.code} (действителен ${Math.round(data.expires_in_seconds / 60)} мин.)`)
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Ошибка создания кода')
    } finally {
      setLinkCodeLoading(false)
    }
  }

  const handleDelete = () => {
    onDelete(user)
    setDeleteOpen(false)
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Вход в панель</CardTitle>
          <CardDescription>
            Доступ абонента к админ-панели (не влияет на получение конфигов и Telegram).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between gap-3 rounded-xl border bg-muted/20 p-3">
            <div className="space-y-0.5">
              <Label>Разрешить вход в панель</Label>
              <p className="text-xs text-muted-foreground">
                Выкл. — абонент не сможет войти под своим логином
              </p>
            </div>
            <Switch id="accountPanelLogin" checked={panelLogin} onCheckedChange={setPanelLogin} />
          </div>
          <div className="rounded-xl border bg-muted/20 p-3">
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
          <Button type="button" onClick={handleSave}>
            {panelLogin !== Boolean(user.panel_login_enabled) || password.trim().length > 0
              ? 'Сохранить'
              : 'Изменений нет'}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Квота конфигов</CardTitle>
          <CardDescription>
            Лимит имён конфигов на всех серверах (имена, не файлы).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-semibold">{used}</span>
            {limit != null ? (
              <>
                <span className="text-muted-foreground font-normal"> из </span>
                <span className="text-muted-foreground font-normal">{limit}</span>
              </>
            ) : (
              <span className="text-muted-foreground font-normal"> из ∞</span>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            {limit == null ? 'Без лимита — действует общий лимит панели.' : 'Достижение квоты блокирует добавление имён.'}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Привязка Telegram</CardTitle>
          <CardDescription>
            Код для команды `/link` в боте. Действует 10 минут.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button type="button" onClick={handleCreateLinkCode} disabled={linkCodeLoading} className="w-full sm:w-auto">
            {linkCodeLoading ? 'Создание…' : <><Phone size={15} /> Получить код привязки</>}
          </Button>
          {linkCode && (
            <div className="rounded-lg border bg-muted/20 p-3 flex items-center justify-between gap-2 mt-2">
              <span className="font-mono text-sm font-medium">{linkCode}</span>
              <Button type="button" size="sm" variant="outline" onClick={() => setLinkCode(null)}>
                Скрыть
              </Button>
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            Код для команды <code className="font-mono">/link</code> в боте. Действует 10 минут.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Удаление аккаунта</CardTitle>
          <CardDescription>
            Удалить абонента и все его конфиги. Необратимо.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <Button type="button" variant="destructive" onClick={() => setDeleteOpen(true)} className="w-full sm:w-auto">
            <Trash2 size={15} />
            Удалить пользователя
          </Button>
        </CardContent>
      </Card>

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
