import { FormEvent, useEffect, useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { LogIn, Shield } from 'lucide-react'
import { ApiError, getCaptchaRequired, getTelegramLoginConfig, loginWithCaptcha } from '@/api/client'
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
  const [captchaRequired, setCaptchaRequired] = useState(false)
  const [captchaKey, setCaptchaKey] = useState(0)
  const [tgBot, setTgBot] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    const token = searchParams.get('token')
    if (token && setToken) {
      setToken(token)
    }
  }, [searchParams, setToken])

  useEffect(() => {
    getCaptchaRequired()
      .then((d) => setCaptchaRequired(d.required))
      .catch(() => {})
    getTelegramLoginConfig()
      .then((d) => {
        if (d.enabled && d.bot_username) setTgBot(d.bot_username)
      })
      .catch(() => {})
  }, [])

  const refreshCaptcha = async () => {
    const resp = await fetch(`${API_BASE}/auth/captcha`)
    const id = resp.headers.get('X-Captcha-Id') || ''
    setCaptchaId(id)
    setCaptchaKey((k) => k + 1)
    setCaptchaRequired(true)
  }

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
      if (captchaRequired && captchaId) {
        const res = await loginWithCaptcha(username, password, captchaId, captchaText)
        if (setToken) setToken(res.access_token)
        else await login(username, password)
      } else {
        await login(username, password)
      }
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Ошибка входа'
      notifyError(msg)
      if (msg.includes('капч')) {
        await refreshCaptcha()
        setCaptchaRequired(true)
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
            {captchaRequired && (
              <div className="space-y-2">
                <Label>Капча</Label>
                <div className="flex items-center gap-2">
                  <img
                    key={captchaKey}
                    src={`${API_BASE}/auth/captcha?${captchaKey}`}
                    alt="captcha"
                    className="h-12 rounded border"
                    onLoad={(e) => {
                      const id = (e.target as HTMLImageElement).getAttribute('data-captcha-id')
                      if (!captchaId && id) setCaptchaId(id)
                    }}
                    ref={(img) => {
                      if (img && !captchaId) {
                        fetch(`${API_BASE}/auth/captcha`)
                          .then((r) => {
                            const id = r.headers.get('X-Captcha-Id') || ''
                            setCaptchaId(id)
                            return r.blob()
                          })
                          .then((b) => {
                            if (img) img.src = URL.createObjectURL(b)
                          })
                          .catch(() => {})
                      }
                    }}
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
