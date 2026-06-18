import { useEffect, useState } from 'react'
import { Fingerprint, Trash2 } from 'lucide-react'
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
import type { PasskeyCredential } from '@/api/client'

export default function PasskeysTab() {
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
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Fingerprint size={18} />
          Passkeys
        </CardTitle>
        <CardDescription>
          Фишинг-resistant вход через Touch ID, Windows Hello или USB-ключ (опционально вместе с TOTP)
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <InlineProgressBar active={loading} label="Обработка..." />

        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={credentials.length > 0 ? 'default' : 'secondary'}>
            {credentials.length > 0 ? `Зарегистрировано: ${credentials.length}` : 'Не настроено'}
          </Badge>
        </div>

        <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-end">
          <div className="grid gap-2">
            <Label htmlFor="passkey-nickname">Название (необязательно)</Label>
            <Input
              id="passkey-nickname"
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
              placeholder="MacBook, YubiKey..."
              maxLength={128}
            />
          </div>
          <Button type="button" onClick={() => void handleRegister()} disabled={loading}>
            Добавить passkey
          </Button>
        </div>

        {credentials.length > 0 && (
          <ul className="space-y-2">
            {credentials.map((item) => (
              <li
                key={item.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3"
              >
                <div>
                  <p className="font-medium">{item.nickname}</p>
                  <p className="text-xs text-muted-foreground">
                    Создан: {formatDateTime(item.created_at)}
                    {item.last_used_at
                      ? ` · Последний вход: ${formatDateTime(item.last_used_at)}`
                      : ''}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => void handleRename(item.id, item.nickname)}
                    disabled={loading}
                  >
                    Переименовать
                  </Button>
                  <Button
                    type="button"
                    variant="destructive"
                    size="sm"
                    onClick={() => void handleDelete(item.id)}
                    disabled={loading}
                  >
                    <Trash2 size={14} />
                    Удалить
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
