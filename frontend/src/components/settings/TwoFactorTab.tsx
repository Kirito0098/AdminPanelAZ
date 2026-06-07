import { useEffect, useState } from 'react'
import { Copy, KeyRound, ShieldCheck } from 'lucide-react'
import {
  ApiError,
  disable2FA,
  enable2FA,
  get2FAStatus,
  regenerate2FABackupCodes,
  setup2FA,
} from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { useNotifications } from '@/context/NotificationContext'

function formatSecretForDisplay(secret: string): string {
  return secret.match(/.{1,4}/g)?.join(' ') ?? secret
}

export default function TwoFactorTab() {
  const { success, error: notifyError } = useNotifications()
  const [enabled, setEnabled] = useState(false)
  const [backupRemaining, setBackupRemaining] = useState(0)
  const [setupData, setSetupData] = useState<{ secret: string; qr_data_url: string } | null>(null)
  const [verifyCode, setVerifyCode] = useState('')
  const [backupCodes, setBackupCodes] = useState<string[]>([])
  const [loading, setLoading] = useState(false)

  const load = async () => {
    try {
      const status = await get2FAStatus()
      setEnabled(status.enabled)
      setBackupRemaining(status.backup_codes_remaining)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки 2FA')
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleSetup = async () => {
    setLoading(true)
    try {
      const data = await setup2FA()
      setSetupData({ secret: data.secret, qr_data_url: data.qr_data_url })
      setBackupCodes([])
      success('Отсканируйте QR-код в приложении аутентификатора')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка настройки 2FA')
    } finally {
      setLoading(false)
    }
  }

  const handleEnable = async () => {
    setLoading(true)
    try {
      const res = await enable2FA(verifyCode)
      setBackupCodes(res.backup_codes)
      setSetupData(null)
      setVerifyCode('')
      success('2FA включена')
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Неверный код')
    } finally {
      setLoading(false)
    }
  }

  const handleDisable = async () => {
    setLoading(true)
    try {
      await disable2FA(verifyCode)
      setVerifyCode('')
      setBackupCodes([])
      success('2FA отключена')
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Неверный код')
    } finally {
      setLoading(false)
    }
  }

  const handleRegenerate = async () => {
    setLoading(true)
    try {
      const res = await regenerate2FABackupCodes(verifyCode)
      setBackupCodes(res.backup_codes)
      setVerifyCode('')
      success('Резервные коды обновлены')
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Неверный код')
    } finally {
      setLoading(false)
    }
  }

  const handleCopySecret = async () => {
    if (!setupData) return
    try {
      await navigator.clipboard.writeText(setupData.secret)
      success('Секретный ключ скопирован')
    } catch {
      notifyError('Не удалось скопировать ключ')
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldCheck size={18} />
          Двухфакторная аутентификация (2FA)
        </CardTitle>
        <CardDescription>
          TOTP для администраторов (Google Authenticator, Authy и др.)
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <InlineProgressBar active={loading} label="Обработка..." />

        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={enabled ? 'default' : 'secondary'}>
            {enabled ? 'Включена' : 'Выключена'}
          </Badge>
          {enabled && backupRemaining > 0 && (
            <span className="text-sm text-muted-foreground">Резервных кодов: {backupRemaining}</span>
          )}
        </div>

        {!enabled && !setupData && (
          <Button onClick={handleSetup} disabled={loading}>
            <KeyRound size={16} />
            Настроить 2FA
          </Button>
        )}

        {setupData && (
          <div className="space-y-3 rounded-lg border p-4">
            <img src={setupData.qr_data_url} alt="QR 2FA" className="mx-auto h-40 w-40" />
            <div className="rounded-lg border bg-muted/50 p-3 sm:p-4">
              <p className="mb-2 text-center text-xs text-muted-foreground">Ключ для ручного ввода</p>
              <div className="flex flex-col items-stretch gap-2 sm:flex-row sm:items-center sm:justify-center">
                <code className="select-all break-all rounded-md bg-background px-3 py-2 text-center font-mono text-sm leading-relaxed tracking-wide text-foreground sm:text-base">
                  {formatSecretForDisplay(setupData.secret)}
                </code>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="shrink-0"
                  onClick={() => void handleCopySecret()}
                >
                  <Copy size={14} />
                  Копировать
                </Button>
              </div>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="2fa-enable-code">Код из приложения</Label>
              <Input
                id="2fa-enable-code"
                value={verifyCode}
                onChange={(e) => setVerifyCode(e.target.value.replace(/\s/g, ''))}
                placeholder="123456"
                maxLength={8}
              />
            </div>
            <Button onClick={handleEnable} disabled={loading || verifyCode.length < 6}>
              Подтвердить и включить
            </Button>
          </div>
        )}

        {enabled && (
          <div className="space-y-3">
            <div className="grid gap-2">
              <Label htmlFor="2fa-code">Код 2FA</Label>
              <Input
                id="2fa-code"
                value={verifyCode}
                onChange={(e) => setVerifyCode(e.target.value.replace(/\s/g, ''))}
                placeholder="123456 или резервный код"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="destructive" onClick={handleDisable} disabled={loading}>
                Отключить 2FA
              </Button>
              <Button variant="outline" onClick={handleRegenerate} disabled={loading}>
                Новые резервные коды
              </Button>
            </div>
          </div>
        )}

        {backupCodes.length > 0 && (
          <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4">
            <p className="mb-2 text-sm font-medium">Сохраните резервные коды (одноразовые):</p>
            <ul className="grid grid-cols-2 gap-1 font-mono text-xs">
              {backupCodes.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
