import { FormEvent, useEffect, useState } from 'react'
import { Activity, Save } from 'lucide-react'
import { ApiError, getMonitorSettings, updateMonitorSettings } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useNotifications } from '@/context/NotificationContext'

export default function MonitorSettingsCard() {
  const { success, error: notifyError } = useNotifications()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [cpu, setCpu] = useState(90)
  const [ram, setRam] = useState(90)
  const [intervalSec, setIntervalSec] = useState(60)
  const [cooldownMin, setCooldownMin] = useState(30)
  const [sustainedSec, setSustainedSec] = useState(180)

  useEffect(() => {
    getMonitorSettings()
      .then((data) => {
        setCpu(data.cpu_threshold)
        setRam(data.ram_threshold)
        setIntervalSec(data.interval_seconds)
        setCooldownMin(data.cooldown_minutes)
        setSustainedSec(data.sustained_seconds)
      })
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки мониторинга'))
      .finally(() => setLoading(false))
  }, [notifyError])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const updated = await updateMonitorSettings({
        cpu_threshold: cpu,
        ram_threshold: ram,
        interval_seconds: intervalSec,
        cooldown_minutes: cooldownMin,
        sustained_seconds: sustainedSec,
      })
      setCpu(updated.cpu_threshold)
      setRam(updated.ram_threshold)
      setIntervalSec(updated.interval_seconds)
      setCooldownMin(updated.cooldown_minutes)
      setSustainedSec(updated.sustained_seconds)
      success('Настройки мониторинга сохранены')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <Spinner label="Загрузка настроек мониторинга..." className="py-8" />
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Activity size={18} />
          Мониторинг CPU/RAM
        </CardTitle>
        <CardDescription>
          Пороги Telegram-оповещений, длительность высокой нагрузки и интервал проверки ресурсов узла
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="monitor-cpu">Порог CPU, %</Label>
              <Input
                id="monitor-cpu"
                type="number"
                min={1}
                max={100}
                value={cpu}
                onChange={(e) => setCpu(Number(e.target.value))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="monitor-ram">Порог RAM, %</Label>
              <Input
                id="monitor-ram"
                type="number"
                min={1}
                max={100}
                value={ram}
                onChange={(e) => setRam(Number(e.target.value))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="monitor-interval">Интервал проверки, сек</Label>
              <Input
                id="monitor-interval"
                type="number"
                min={10}
                max={3600}
                value={intervalSec}
                onChange={(e) => setIntervalSec(Number(e.target.value))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="monitor-cooldown">Cooldown оповещений, мин</Label>
              <Input
                id="monitor-cooldown"
                type="number"
                min={1}
                max={1440}
                value={cooldownMin}
                onChange={(e) => setCooldownMin(Number(e.target.value))}
              />
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="monitor-sustained">Мин. длительность высокой нагрузки, сек</Label>
              <Input
                id="monitor-sustained"
                type="number"
                min={0}
                max={3600}
                value={sustainedSec}
                onChange={(e) => setSustainedSec(Number(e.target.value))}
              />
              <p className="text-xs text-muted-foreground">
                Алерт отправляется только если CPU/RAM держатся выше порога не менее этого времени (0 — сразу).
                При интервале 60 сек и значении 180 — около 3 подряд высоких замеров.
              </p>
            </div>
          </div>
          <SettingsAlert variant="info" title="Применение">
            Значения сохраняются в backend/.env. Для полного применения может потребоваться перезапуск панели.
          </SettingsAlert>
          <Button type="submit" disabled={saving}>
            <Save size={16} />
            {saving ? 'Сохранение...' : 'Сохранить'}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
