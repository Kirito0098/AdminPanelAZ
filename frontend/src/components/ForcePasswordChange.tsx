import { FormEvent, useState } from 'react'
import { KeyRound } from 'lucide-react'
import { ApiError, changePassword } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/context/AuthContext'
import { useNotifications } from '@/context/NotificationContext'

export default function ForcePasswordChange() {
  const { user, refreshUser } = useAuth()
  const { success, error: notifyError } = useNotifications()
  const [currentPwd, setCurrentPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [confirmPwd, setConfirmPwd] = useState('')
  const [saving, setSaving] = useState(false)

  if (!user?.must_change_password) return null

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (newPwd !== confirmPwd) {
      notifyError('Пароли не совпадают')
      return
    }
    setSaving(true)
    try {
      await changePassword(currentPwd, newPwd)
      await refreshUser()
      success('Пароль изменён')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка смены пароля')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4 backdrop-blur">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound size={20} />
            Смените пароль
          </CardTitle>
          <CardDescription>Для безопасности необходимо сменить пароль по умолчанию</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="forceCurrent">Текущий пароль</Label>
              <Input
                id="forceCurrent"
                type="password"
                value={currentPwd}
                onChange={(e) => setCurrentPwd(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="forceNew">Новый пароль</Label>
              <Input
                id="forceNew"
                type="password"
                value={newPwd}
                onChange={(e) => setNewPwd(e.target.value)}
                required
                minLength={8}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="forceConfirm">Подтверждение</Label>
              <Input
                id="forceConfirm"
                type="password"
                value={confirmPwd}
                onChange={(e) => setConfirmPwd(e.target.value)}
                required
                minLength={8}
              />
            </div>
            <Button type="submit" className="w-full" disabled={saving}>
              {saving ? 'Сохранение...' : 'Сохранить пароль'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
