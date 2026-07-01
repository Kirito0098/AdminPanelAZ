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
import { LABEL_COOLDOWN_MIN } from '@/lib/uiLabels'

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
          Нагрузка на сервер
        </CardTitle>
        <CardDescription>
          Когда предупреждать в Telegram, если процессор или память долго загружены
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="monitor-cpu">Процессор (CPU), %</Label>
              <Input
                id="monitor-cpu"
                type="number"
                min={1}
                max={100}
                value={cpu}
                onChange={(e) => setCpu(Number(e.target.value))}
              />
              <p className="text-xs text-muted-foreground">Уведомить, если загрузка выше этого значения</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="monitor-ram">Память (RAM), %</Label>
              <Input
                id="monitor-ram"
                type="number"
                min={1}
                max={100}
                value={ram}
                onChange={(e) => setRam(Number(e.target.value))}
              />
              <p className="text-xs text-muted-foreground">Уведомить, если занято больше этого процента</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="monitor-interval">Как часто проверять (секунды)</Label>
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
              <Label htmlFor="monitor-cooldown">{LABEL_COOLDOWN_MIN}</Label>
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
              <Label htmlFor="monitor-sustained">Сколько держаться высокой нагрузке (секунды)</Label>
              <Input
                id="monitor-sustained"
                type="number"
                min={0}
                max={3600}
                value={sustainedSec}
                onChange={(e) => setSustainedSec(Number(e.target.value))}
              />
              <p className="text-xs text-muted-foreground">
                Уведомление придёт только если нагрузка не снижается указанное время. 0 — сообщать сразу.
                При проверке каждые 60 сек и значении 180 — примерно 3 замера подряд.
              </p>
            </div>
          </div>
          <SettingsAlert variant="info" title="После сохранения">
            Новые пороги начнут действовать сразу. В редких случаях может понадобиться перезапуск панели.
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
