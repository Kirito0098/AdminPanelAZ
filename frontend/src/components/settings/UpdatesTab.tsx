import { useEffect, useState } from 'react'
import { Download, RefreshCw } from 'lucide-react'
import { ApiError, applySystemUpdate, checkSystemUpdates } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useNotifications } from '@/context/NotificationContext'

export default function UpdatesTab() {
  const { success, error: notifyError } = useNotifications()
  const [info, setInfo] = useState<{
    updates_available?: boolean
    commits_behind?: number
    local_hash?: string
    remote_hash?: string
    error?: string
  } | null>(null)
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      setInfo(await checkSystemUpdates())
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка проверки обновлений')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleUpdate = async () => {
    if (!confirm('Применить git pull origin main?')) return
    setUpdating(true)
    try {
      const res = await applySystemUpdate()
      success(res.message || 'Обновление применено')
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка обновления')
    } finally {
      setUpdating(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Download size={18} />
          Системные обновления
        </CardTitle>
        <CardDescription>Git fetch + pull из origin/main</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={load} disabled={loading}>
            <RefreshCw size={16} />
            Проверить
          </Button>
          {info?.updates_available ? (
            <Badge variant="destructive">{info.commits_behind} коммит(ов) позади</Badge>
          ) : (
            <Badge variant="secondary">Актуально</Badge>
          )}
        </div>
        {info && (
          <div className="grid gap-2 text-sm md:grid-cols-2">
            <div>Локальный: {info.local_hash || '—'}</div>
            <div>Удалённый: {info.remote_hash || '—'}</div>
          </div>
        )}
        {info?.updates_available && (
          <Button onClick={handleUpdate} disabled={updating}>
            {updating ? 'Обновление...' : 'Применить обновление'}
          </Button>
        )}
        {info?.error && <p className="text-sm text-destructive">{info.error}</p>}
      </CardContent>
    </Card>
  )
}
