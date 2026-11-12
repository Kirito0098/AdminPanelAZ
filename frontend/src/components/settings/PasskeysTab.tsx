import { useEffect, useState, type ReactNode } from 'react'
import { Fingerprint, Pencil, Plus, Trash2 } from 'lucide-react'
import {
  ApiError,
  deletePasskey,
  getPasskeys,
  getPasskeyRegisterOptions,
  renamePasskey,
  verifyPasskeyRegister,
} from '@/api/client'
import { formatDateTime } from '@/lib/datetime'
import { passkeyDeleteConfirm } from '@/lib/passkeyConfirm'
import { registerPasskey } from '@/lib/passkeys'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  SettingsCard as Card,
  SettingsCardContent as CardContent,
  SettingsCardDescription as CardDescription,
  SettingsCardHeader as CardHeader,
  SettingsCardTitle as CardTitle,
} from '@/components/settings/SettingsCard'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { useNotifications } from '@/context/NotificationContext'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { cn } from '@/lib/utils'
import type { PasskeyCredential } from '@/api/client'

function ListRow({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <li className="flex items-center justify-between gap-3 rounded-lg border border-border/70 bg-muted/20 px-3 py-2.5 transition-colors hover:bg-muted/40">
      <div className="min-w-0 flex-1">{children}</div>
      {action ? <div className="flex shrink-0 gap-2">{action}</div> : null}
    </li>
  )
}

export default function PasskeysTab({ className }: { className?: string }) {
  const { success, error: notifyError } = useNotifications()
  const { confirm, dialogProps } = useConfirmDialog()
  const [credentials, setCredentials] = useState<PasskeyCredential[]>([])
  const [loading, setLoading] = useState(false)
  const [nickname, setNickname] = useState('')

  const load = async () => {
    try {
      const data = await getPasskeys()
      setCredentials(data.credentials)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки passkeys')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const handleRegister = async () => {
    setLoading(true)
    try {
      const { options } = await getPasskeyRegisterOptions()
      const { sessionKey, credential } = await registerPasskey(options)
      await verifyPasskeyRegister(sessionKey, credential, nickname.trim() || undefined)
      setNickname('')
      success('Passkey добавлен')
      await load()
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Не удалось зарегистрировать passkey'
      notifyError(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (id: number) => {
    setLoading(true)
    try {
      await deletePasskey(id)
      success('Passkey удалён')
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка удаления')
    } finally {
      setLoading(false)
    }
  }

  const confirmDelete = (item: PasskeyCredential) => {
    confirm({
      ...passkeyDeleteConfirm(item.nickname),
      destructive: true,
      onConfirm: () => handleDelete(item.id),
    })
  }

  const handleRename = async (id: number, current: string) => {
    const next = window.prompt('Название passkey', current)
    if (!next || next.trim() === current) return
    setLoading(true)
    try {
      await renamePasskey(id, next.trim())
      success('Passkey переименован')
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка переименования')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className={cn('flex h-full flex-col', className)}>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Fingerprint size={16} aria-hidden />
          </span>
          <div className="min-w-0">
            <CardTitle>Вход по отпечатку или ключу</CardTitle>
            <CardDescription className="mt-0.5">
              Touch ID, Face ID, Windows Hello или USB-ключ
            </CardDescription>
          </div>
        </div>
        <Badge
          variant={credentials.length > 0 ? 'success' : 'secondary'}
          className="shrink-0 tabular-nums"
        >
          {credentials.length > 0 ? credentials.length : '0'}
        </Badge>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col space-y-4">
        <InlineProgressBar active={loading} label="Обработка..." />

        <div className="rounded-lg border border-border/70 bg-muted/20 p-3 sm:p-4">
          <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
            <div className="space-y-2">
              <Label htmlFor="passkey-nickname">Название (необязательно)</Label>
              <Input
                id="passkey-nickname"
                value={nickname}
                onChange={(e) => setNickname(e.target.value)}
                placeholder="MacBook, YubiKey..."
                maxLength={128}
              />
            </div>
            <Button type="button" onClick={() => void handleRegister()} disabled={loading} className="gap-1.5">
              <Plus size={16} />
              Добавить
            </Button>
          </div>
        </div>

        {credentials.length > 0 ? (
          <ul className="space-y-2">
            {credentials.map((item) => (
              <ListRow
                key={item.id}
                action={
                  <>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => void handleRename(item.id, item.nickname)}
                      disabled={loading}
                      title="Переименовать"
                    >
                      <Pencil size={14} />
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      className="h-8 w-8 border-destructive/30 text-destructive hover:bg-destructive/10"
                      onClick={() => confirmDelete(item)}
                      disabled={loading}
                      title="Удалить"
                    >
                      <Trash2 size={14} />
                    </Button>
                  </>
                }
              >
                <div className="flex items-center gap-2">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
                    <Fingerprint size={16} />
                  </div>
                  <div className="min-w-0">
                    <p className="truncate font-medium">{item.nickname}</p>
                    <p className="text-xs text-muted-foreground">
                      Создан: {formatDateTime(item.created_at)}
                      {item.last_used_at ? ` · Вход: ${formatDateTime(item.last_used_at)}` : ''}
                    </p>
                  </div>
                </div>
              </ListRow>
            ))}
          </ul>
        ) : (
          <p className="rounded-lg border border-dashed border-border/70 px-4 py-6 text-center text-xs text-muted-foreground">
            Passkey не настроен — добавьте ключ или биометрию для быстрого входа
          </p>
        )}
      </CardContent>
      <ConfirmDialogHost dialogProps={dialogProps} />
    </Card>
  )
}
