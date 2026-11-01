import { useState } from 'react'
import { KeyRound, Layers, LogIn, Phone, ShieldCheck, StickyNote, Trash2, Copy } from 'lucide-react'
import { createUserTelegramLinkCode } from '@/api/users'
import { ApiError, updateUser } from '@/api/client'
import UnlockCodeCreateDialog from '@/components/dashboard/UnlockCodeCreateDialog'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PercentBar } from '@/components/ui/percent-bar'
import { Switch } from '@/components/ui/switch'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import type { UserProvisionSummary, UserUpdatePayload } from '@/types'
import UserSection from './UserSection'
import UserVisibilitySection from './UserVisibilitySection'

interface UserAccountSectionProps {
  user: UserProvisionSummary
  onSave: (id: number, data: Partial<UserUpdatePayload>) => void
  onDelete: (user: UserProvisionSummary) => void
  onRefresh: () => void
}

/** Права абонента на свои конфиги в Telegram Mini App и веб-панели. */
function MiniAppRightsSection({
  user,
  onRefresh,
}: {
  user: UserProvisionSummary
  onRefresh: () => void
}) {
  const { success, error: notifyError } = useNotifications()
  const [canCreate, setCanCreate] = useState(user.can_create_configs !== false)
  const [canManage, setCanManage] = useState(user.can_manage_configs === true)
  const [saving, setSaving] = useState(false)

  const save = async (
    data: { can_create_configs?: boolean; can_manage_configs?: boolean },
    message: string,
    rollback: () => void,
  ) => {
    setSaving(true)
    try {
      await updateUser(user.id, data)
      success(message)
      onRefresh()
    } catch (err) {
      rollback()
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения прав')
    } finally {
      setSaving(false)
    }
  }

  const toggleCreate = (next: boolean) => {
    setCanCreate(next)
    void save(
      { can_create_configs: next },
      next ? 'Создание конфигураций разрешено' : 'Создание конфигураций запрещено',
      () => setCanCreate(!next),
    )
  }

  const toggleManage = (next: boolean) => {
    setCanManage(next)
    void save(
      { can_manage_configs: next },
      next ? 'Управление конфигурациями разрешено' : 'Управление конфигурациями запрещено',
      () => setCanManage(!next),
    )
  }

  return (
    <UserSection
      icon={ShieldCheck}
      title="Права в Mini App"
      description="Что абонент может делать со своими конфигами в Telegram Mini App и веб-панели."
    >
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-3 rounded-lg border bg-muted/20 px-3 py-2.5">
          <div className="space-y-0.5">
            <Label htmlFor="accountCanCreate">Может создавать конфигурации</Label>
            <p className="text-xs text-muted-foreground">
              Выкл. — только просмотр и скачивание своих конфигов.
            </p>
          </div>
          <Switch
            id="accountCanCreate"
            checked={canCreate}
            disabled={saving}
            onCheckedChange={toggleCreate}
          />
        </div>
        <div className="flex items-center justify-between gap-3 rounded-lg border bg-muted/20 px-3 py-2.5">
          <div className="space-y-0.5">
            <Label htmlFor="accountCanManage">Может управлять конфигурациями</Label>
            <p className="text-xs text-muted-foreground">
              Выкл. — только получение и скачивание: продление сертификата и удаление недоступны.
            </p>
          </div>
          <Switch
            id="accountCanManage"
            checked={canManage}
            disabled={saving}
            onCheckedChange={toggleManage}
          />
        </div>
      </div>
    </UserSection>
  )
}

export default function UserAccountSection({ user, onSave, onDelete, onRefresh }: UserAccountSectionProps) {
  const { error: notifyError, success } = useNotifications()
  const { isEnabled } = useFeatureModules()
  const [unlockOpen, setUnlockOpen] = useState(false)
  const unlockProtocols = (
    [
      { id: 'openvpn', keys: ['openvpn'] },
      { id: 'wireguard', keys: ['wireguard', 'amneziawg'] },
      { id: 'amneziawg2', keys: ['awg2'] },
    ] as const
  )
    .filter((p) => p.keys.some((k) => isEnabled(k)))
    .map((p) => p.id)
  const [panelLogin, setPanelLogin] = useState(Boolean(user.panel_login_enabled))
  const [password, setPassword] = useState('')
  const [linkCode, setLinkCode] = useState<string | null>(null)
  const [linkCodeLoading, setLinkCodeLoading] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [note, setNote] = useState(user.note ?? '')
  const [noteSaving, setNoteSaving] = useState(false)
  const [quotaInput, setQuotaInput] = useState(
    user.config_quota != null ? String(user.config_quota) : '',
  )
  const [quotaSaving, setQuotaSaving] = useState(false)

  const used = user.plan_config_indexes?.length ?? 0
  const limit = user.config_quota ?? null
  const quotaPercent = limit && limit > 0 ? Math.min((used / limit) * 100, 100) : 0
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
      success(`Код привязки Telegram: ${data.code} (действителен ${Math.round(data.expires_in_seconds / 60)} мин.)`)
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Ошибка создания кода')
    } finally {
      setLinkCodeLoading(false)
    }
  }

  const handleCopyLinkCode = async () => {
    if (!linkCode) return
    try {
      await navigator.clipboard.writeText(linkCode)
      success('Код скопирован')
    } catch {
      notifyError('Не удалось скопировать код')
    }
  }

  const handleDelete = () => {
    onDelete(user)
    setDeleteOpen(false)
  }

  const handleSaveNote = async () => {
    setNoteSaving(true)
    try {
      await updateUser(user.id, { note: note.trim() ? note.trim() : null })
      success('Заметка сохранена')
      onRefresh()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось сохранить заметку')
    } finally {
      setNoteSaving(false)
    }
  }

  const handleSaveQuota = async () => {
    const trimmed = quotaInput.trim()
    let value: number | null = null
    if (trimmed) {
      const parsed = Number.parseInt(trimmed, 10)
      if (!Number.isFinite(parsed) || parsed < 0) {
        notifyError('Квота — целое число ≥ 0 или пусто')
        return
      }
      value = parsed
    }
    setQuotaSaving(true)
    try {
      await updateUser(user.id, { config_quota: value })
      success('Квота сохранена')
      onRefresh()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось сохранить квоту')
    } finally {
      setQuotaSaving(false)
    }
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
          <Button type="button" onClick={() => void handleSaveNote()} disabled={noteSaving}>
            {noteSaving ? 'Сохранение…' : 'Сохранить заметку'}
          </Button>
        </div>
      </UserSection>

      {user.role === 'user' && <UserVisibilitySection user={user} onRefresh={onRefresh} />}
      {user.role === 'user' && <MiniAppRightsSection user={user} onRefresh={onRefresh} />}

      <UserSection
        icon={Layers}
        title="Квота конфигов"
        description="Лимит имён конфигов на всех серверах."
        actions={
          <Badge variant="secondary">
            {used} / {limit ?? '∞'}
          </Badge>
        }
      >
        <div className="space-y-2">
          {limit != null && limit > 0 && (
            <PercentBar
              value={used}
              max={limit}
              className="h-2"
              barClassName={quotaPercent >= 100 ? 'fill-destructive' : quotaPercent >= 80 ? 'fill-amber-500' : 'fill-primary'}
              label="Использование квоты конфигов"
            />
          )}
          <p className="text-xs text-muted-foreground">
            {limit == null
              ? 'Без личной квоты — действует общий лимит панели.'
              : 'Достижение квоты блокирует добавление имён.'}
          </p>
          <div className="flex items-end gap-2">
            <div className="space-y-1">
              <Label htmlFor="quotaInput">Квота конфигов</Label>
              <Input
                id="quotaInput"
                inputMode="numeric"
                value={quotaInput}
                onChange={(e) => setQuotaInput(e.target.value)}
                placeholder="без квоты"
                className="h-9 w-32"
              />
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={() => void handleSaveQuota()}
              disabled={quotaSaving}
            >
              Сохранить
            </Button>
          </div>
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
              <span className="font-mono text-sm font-medium">{linkCode}</span>
              <div className="flex items-center gap-1">
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8"
                  onClick={() => void handleCopyLinkCode()}
                  aria-label="Скопировать код привязки"
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

      {isEnabled('unlock_codes') && unlockProtocols.length > 0 ? (
        <UserSection
          icon={KeyRound}
          title="Ключ продления"
          description="Создать unlock-ключ для абонента и отправить в Telegram, если он привязан."
        >
          <Button
            type="button"
            onClick={() => setUnlockOpen(true)}
            className="w-full sm:w-auto"
          >
            <KeyRound size={15} /> Создать ключ
          </Button>
        </UserSection>
      ) : null}

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

      {isEnabled('unlock_codes') && unlockProtocols.length > 0 ? (
        <UnlockCodeCreateDialog
          open={unlockOpen}
          onOpenChange={setUnlockOpen}
          availableProtocols={unlockProtocols}
          initialProtocols={unlockProtocols}
          boundUser={{ id: user.id, username: user.username }}
          telegramBound={Boolean(user.telegram_id)}
          targetUserId={user.id}
          onCreated={() => onRefresh()}
        />
      ) : null}

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
