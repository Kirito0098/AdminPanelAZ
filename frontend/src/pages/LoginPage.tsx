import { FormEvent, useEffect, useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { LogIn, Shield } from 'lucide-react'
import {
  ApiError,
  getCaptchaRequired,
  getFeatureModules,
  getTelegramLoginConfig,
  login2FA,
  loginWithCaptcha,
} from '@/api/client'
import { storeWebSessionId } from '@/lib/webSession'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import Spinner from '@/components/ui/Spinner'
import { useAuth } from '@/context/AuthContext'
import { useNotifications } from '@/context/NotificationContext'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

export default function LoginPage() {
  const { user, login, loading, setToken } = useAuth()
  const { error: notifyError } = useNotifications()
  const [searchParams] = useSearchParams()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [captchaText, setCaptchaText] = useState('')
  const [captchaId, setCaptchaId] = useState('')
  const [captchaImageUrl, setCaptchaImageUrl] = useState('')
  const [captchaRequired, setCaptchaRequired] = useState(false)
  const [tgBot, setTgBot] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [needs2FA, setNeeds2FA] = useState(false)
  const [tempToken, setTempToken] = useState('')
  const [totpCode, setTotpCode] = useState('')

  useEffect(() => {
    const hashToken = window.location.hash.match(/^#token=(.+)$/)?.[1]
    const queryToken = searchParams.get('token')
    const token = hashToken || queryToken
    if (token && setToken) {
      setToken(decodeURIComponent(token))
      if (hashToken) {
        window.history.replaceState(null, '', window.location.pathname + window.location.search)
      }
    }
  }, [searchParams, setToken])

  const refreshCaptcha = async () => {
    const resp = await fetch(`${API_BASE}/auth/captcha`)
    const id = resp.headers.get('X-Captcha-Id') || ''
    const blob = await resp.blob()
    setCaptchaId(id)
    setCaptchaImageUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev)
      return URL.createObjectURL(blob)
    })
    setCaptchaText('')
    setCaptchaRequired(true)
  }

  useEffect(() => {
    getCaptchaRequired()
      .then((d) => {
        setCaptchaRequired(d.required)
        if (d.required) return refreshCaptcha()
      })
      .catch(() => {})
    Promise.all([getFeatureModules().catch(() => null), getTelegramLoginConfig().catch(() => null)])
      .then(([modules, tgConfig]) => {
        const telegramEnabled = modules?.features?.telegram ?? true
        if (telegramEnabled && tgConfig?.enabled && tgConfig.bot_username) {
          setTgBot(tgConfig.bot_username)
        }
      })
  }, [])

  useEffect(() => {
    return () => {
      if (captchaImageUrl) URL.revokeObjectURL(captchaImageUrl)
    }
  }, [captchaImageUrl])

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Spinner label="Загрузка..." />
      </div>
    )
  }

  if (user) return <Navigate to="/" replace />

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      if (needs2FA && tempToken) {
        const res = await login2FA(tempToken, totpCode)
        if (res.web_session_id) storeWebSessionId(res.web_session_id)
        if (setToken) await setToken(res.access_token)
        return
      }
      let res
      if (captchaRequired && captchaId) {
        res = await loginWithCaptcha(username, password, captchaId, captchaText)
      } else {
        res = await login(username, password)
      }
      if ('requires_2fa' in res && res.requires_2fa) {
        setNeeds2FA(true)
        setTempToken(res.temp_token)
        return
      }
      if ('access_token' in res && res.access_token && setToken) {
        await setToken(res.access_token)
      }
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Ошибка входа'
      const needsCaptcha =
        err instanceof ApiError &&
        (err.status === 400 || msg.toLowerCase().includes('капч'))
      try {
        notifyError(msg)
      } catch {
        console.error('Login failed:', msg)
      }
      if (needsCaptcha) {
        setCaptchaRequired(true)
        await refreshCaptcha()
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-background via-background to-primary/5 p-4">
      <Card className="w-full max-w-md shadow-lg">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 flex h-14 w-14 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Shield size={28} />
          </div>
          <CardTitle className="text-2xl">AntiZapret VPN</CardTitle>
          <CardDescription>Панель администрирования</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Логин</Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                placeholder="admin"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Пароль</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                placeholder="••••••••"
                required
              />
            </div>
            {needs2FA && (
              <div className="space-y-2">
                <Label htmlFor="totp">Код 2FA</Label>
                <Input
                  id="totp"
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value.replace(/\s/g, ''))}
                  placeholder="123456"
                  autoComplete="one-time-code"
                  required
                />
              </div>
            )}
            {captchaRequired && !needs2FA && (
              <div className="space-y-2">
                <Label>Капча</Label>
                <div className="flex items-center gap-2">
                  <img
                    src={captchaImageUrl || undefined}
                    alt="captcha"
                    className="h-12 rounded border"
                  />
                  <Button type="button" variant="outline" size="sm" onClick={refreshCaptcha}>
                    ↻
                  </Button>
                </div>
                <Input
                  value={captchaText}
                  onChange={(e) => setCaptchaText(e.target.value.toUpperCase())}
                  placeholder="Код с картинки"
                  required
                />
              </div>
            )}
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? (
                'Вход...'
              ) : (
                <>
                  <LogIn size={16} />
                  Войти
                </>
              )}
            </Button>
            {tgBot && (
              <div className="text-center">
                <script async src="https://telegram.org/js/telegram-widget.js?22" />
                <iframe
                  title="Telegram Login"
                  src={`https://oauth.telegram.org/embed/${tgBot}?origin=${encodeURIComponent(window.location.origin)}&return_to=${encodeURIComponent(`${API_BASE}/auth/telegram`)}`}
                  width="100%"
                  height="44"
                  style={{ border: 'none', overflow: 'hidden' }}
                />
              </div>
            )}
            <p className="text-center text-xs text-muted-foreground">По умолчанию: admin / admin</p>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
