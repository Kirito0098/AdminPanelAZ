import { FormEvent, useEffect, useMemo, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Cpu, MemoryStick, Save } from 'lucide-react'
import { ApiError, getMonitorSettings, updateMonitorSettings } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { SettingsMetaLine, SettingsToolbar } from '@/components/settings/SettingsChrome'
import Spinner from '@/components/ui/Spinner'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useNotifications } from '@/context/NotificationContext'
import { LABEL_COOLDOWN_MIN } from '@/lib/uiLabels'
import { cn } from '@/lib/utils'
import type { MonitorSettings } from '@/types'

const CPU_PRESETS = [70, 80, 90, 95] as const
const RAM_PRESETS = [70, 80, 90, 95] as const
const INTERVAL_PRESETS = [30, 60, 120, 300] as const
const COOLDOWN_PRESETS = [15, 30, 60, 120] as const
const SUSTAINED_PRESETS = [0, 60, 180, 300, 600] as const

function formatInterval(seconds: number) {
  if (seconds < 60) return `${seconds} сек`
  if (seconds % 60 === 0) return `${seconds / 60} мин`
  return `${seconds} сек`
}

function formatSustained(seconds: number) {
  if (seconds === 0) return 'Сразу'
  return formatInterval(seconds)
}

function PresetButtons({
  values,
  selected,
  onSelect,
  format = (v: number) => String(v),
}: {
  values: readonly number[]
  selected: number
  onSelect: (value: number) => void
  format?: (value: number) => string
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {values.map((value) => (
        <button
          key={value}
          type="button"
          onClick={() => onSelect(value)}
          className={cn(
            'rounded-lg border px-3 py-1.5 text-sm font-medium transition-all',
            selected === value
              ? 'border-primary bg-primary/10 text-primary ring-1 ring-primary'
              : 'hover:border-muted-foreground/30 hover:bg-muted/50',
          )}
        >
          {format(value)}
        </button>
      ))}
    </div>
  )
}

function ThresholdField({
  id,
  icon: Icon,
  label,
  hint,
  value,
  presets,
  onChange,
}: {
  id: string
  icon: LucideIcon
  label: string
  hint: string
  value: number
  presets: readonly number[]
  onChange: (value: number) => void
}) {
  return (
    <div className="space-y-3 rounded-xl border bg-muted/15 p-4">
      <div className="flex items-center gap-2">
        <Icon size={16} className="text-muted-foreground" />
        <Label htmlFor={id} className="font-medium">
          {label}
        </Label>
      </div>
      <PresetButtons values={presets} selected={value} onSelect={onChange} format={(v) => `${v}%`} />
      <div className="flex items-center gap-2">
        <Input
          id={id}
          type="number"
          min={1}
          max={100}
          className="h-9 w-20"
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
        />
        <span className="text-xs text-muted-foreground">%</span>
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">{hint}</p>
    </div>
  )
}

export default function MonitorSettingsCard() {
  const { success, error: notifyError } = useNotifications()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState<MonitorSettings | null>(null)
  const [cpu, setCpu] = useState(90)
  const [ram, setRam] = useState(90)
  const [intervalSec, setIntervalSec] = useState(60)
  const [cooldownMin, setCooldownMin] = useState(30)
  const [sustainedSec, setSustainedSec] = useState(180)

  useEffect(() => {
    getMonitorSettings()
      .then((data) => {
        setSaved(data)
        setCpu(data.cpu_threshold)
        setRam(data.ram_threshold)
        setIntervalSec(data.interval_seconds)
        setCooldownMin(data.cooldown_minutes)
        setSustainedSec(data.sustained_seconds)
      })
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки мониторинга'))
      .finally(() => setLoading(false))
  }, [notifyError])

  const isDirty = useMemo(() => {
    if (!saved) return false
    return (
      saved.cpu_threshold !== cpu ||
      saved.ram_threshold !== ram ||
      saved.interval_seconds !== intervalSec ||
      saved.cooldown_minutes !== cooldownMin ||
      saved.sustained_seconds !== sustainedSec
    )
  }, [saved, cpu, ram, intervalSec, cooldownMin, sustainedSec])

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
      setSaved(updated)
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
    return <Spinner label="Загрузка настроек мониторинга..." className="py-12" />
  }

  return (
    <div className="space-y-4">
      <SettingsToolbar
        title="Нагрузка на сервер"
        meta={
          <SettingsMetaLine
            items={[
              { label: 'порог CPU', value: `${cpu}%` },
              { label: 'порог RAM', value: `${ram}%` },
              { label: 'проверка', value: formatInterval(intervalSec) },
              { label: 'удержание', value: formatSustained(sustainedSec) },
            ]}
          />
        }
      />
      <p className="text-sm text-muted-foreground">
        Панель следит за CPU и RAM и шлёт предупреждение в Telegram, если нагрузка долго выше порога
      </p>

      <Card className="shadow-sm">
        <CardContent className="pt-4">
          <InlineProgressBar active={saving} label="Сохранение настроек..." />
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="grid gap-4 md:grid-cols-2">
              <ThresholdField
                id="monitor-cpu"
                icon={Cpu}
                label="Процессор (CPU)"
                hint="Уведомление, если загрузка процессора держится выше порога"
                value={cpu}
                presets={CPU_PRESETS}
                onChange={setCpu}
              />
              <ThresholdField
                id="monitor-ram"
                icon={MemoryStick}
                label="Память (RAM)"
                hint="Уведомление, если занятой памяти больше указанного процента"
                value={ram}
                presets={RAM_PRESETS}
                onChange={setRam}
              />
            </div>

            <div className="grid grid-cols-1 gap-4 rounded-xl border bg-muted/10 p-4 sm:grid-cols-2 lg:grid-cols-3">
              <div className="space-y-3">
                <Label className="text-xs text-muted-foreground">Как часто проверять</Label>
                <PresetButtons
                  values={INTERVAL_PRESETS}
                  selected={intervalSec}
                  onSelect={setIntervalSec}
                  format={formatInterval}
                />
                <div className="flex items-center gap-2">
                  <Input
                    id="monitor-interval"
                    type="number"
                    min={10}
                    max={3600}
                    className="h-9 w-24"
                    value={intervalSec}
                    onChange={(e) => setIntervalSec(Number(e.target.value))}
                  />
                  <span className="text-xs text-muted-foreground">сек</span>
                </div>
              </div>

              <div className="space-y-3">
                <Label className="text-xs text-muted-foreground">{LABEL_COOLDOWN_MIN}</Label>
                <PresetButtons
                  values={COOLDOWN_PRESETS}
                  selected={cooldownMin}
                  onSelect={setCooldownMin}
                  format={(v) => `${v} мин`}
                />
                <div className="flex items-center gap-2">
                  <Input
                    id="monitor-cooldown"
                    type="number"
                    min={1}
                    max={1440}
                    className="h-9 w-20"
                    value={cooldownMin}
                    onChange={(e) => setCooldownMin(Number(e.target.value))}
                  />
                  <span className="text-xs text-muted-foreground">мин</span>
                </div>
              </div>

              <div className="space-y-3">
                <Label className="text-xs text-muted-foreground">Длительность высокой нагрузки</Label>
                <PresetButtons
                  values={SUSTAINED_PRESETS}
                  selected={sustainedSec}
                  onSelect={setSustainedSec}
                  format={formatSustained}
                />
                <div className="flex items-center gap-2">
                  <Input
                    id="monitor-sustained"
                    type="number"
                    min={0}
                    max={3600}
                    className="h-9 w-24"
                    value={sustainedSec}
                    onChange={(e) => setSustainedSec(Number(e.target.value))}
                  />
                  <span className="text-xs text-muted-foreground">сек</span>
                </div>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  0 — сразу после превышения. При интервале {formatInterval(intervalSec)} и значении{' '}
                  {formatSustained(sustainedSec)} — несколько замеров подряд.
                </p>
              </div>
            </div>

            <SettingsAlert variant="info" title="Как это работает">
              Сначала нагрузка должна превысить порог и удержаться заданное время. Повторные сообщения не чаще, чем
              раз в {cooldownMin} мин.
            </SettingsAlert>

            <div className="flex justify-end border-t pt-4">
              <Button type="submit" disabled={saving || !isDirty} className="gap-1.5">
                <Save size={16} />
                {saving ? 'Сохранение...' : 'Сохранить'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
