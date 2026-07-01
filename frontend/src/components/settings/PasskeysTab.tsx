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
import { registerPasskey } from '@/lib/passkeys'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { useNotifications } from '@/context/NotificationContext'
import { cn } from '@/lib/utils'
import type { PasskeyCredential } from '@/api/client'

function ListRow({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <li className="flex items-center justify-between gap-3 rounded-xl border bg-card/50 px-3 py-2.5 transition-colors hover:bg-muted/30">
      <div className="min-w-0 flex-1">{children}</div>
      {action ? <div className="flex shrink-0 gap-2">{action}</div> : null}
    </li>
  )
}

export default function PasskeysTab({ className }: { className?: string }) {
  const { success, error: notifyError } = useNotifications()
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
    <Card className={cn('flex h-full flex-col overflow-hidden shadow-sm', className)}>
      <div
        className={cn(
          'h-1 bg-gradient-to-r',
          credentials.length > 0 ? 'from-cyan-500/70 to-cyan-500/15' : 'from-muted-foreground/30 to-muted/10',
        )}
      />
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0 pb-3">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <Fingerprint size={18} />
            Вход по отпечатку или ключу
          </CardTitle>
          <CardDescription className="mt-1.5">
            Touch ID, Face ID, Windows Hello или USB-ключ
          </CardDescription>
        </div>
        <Badge variant={credentials.length > 0 ? 'success' : 'secondary'} className="shrink-0">
          {credentials.length > 0 ? credentials.length : '0'}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        <InlineProgressBar active={loading} label="Обработка..." />

        <div className="rounded-xl border bg-muted/20 p-4">
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
                      onClick={() => void handleDelete(item.id)}
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
          <p className="text-center text-xs text-muted-foreground">
            Passkey не настроен — добавьте ключ или биометрию для быстрого входа
          </p>
        )}
      </CardContent>
    </Card>
  )
}
