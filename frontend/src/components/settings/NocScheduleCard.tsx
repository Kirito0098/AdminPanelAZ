import { useEffect, useState } from 'react'
import { CalendarClock } from 'lucide-react'
import { ApiError, updateSettings } from '@/api/client'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useAuth } from '@/context/AuthContext'
import { useNotifications } from '@/context/NotificationContext'
import { useTimezone } from '@/context/TimezoneContext'

const DEFAULT_DAILY = '11:00'
const DEFAULT_WEEKLY_DOW = '1'
const DEFAULT_WEEKLY_TIME = '12:00'

const DOW_OPTIONS = [
  { v: '1', l: 'Понедельник' },
  { v: '2', l: 'Вторник' },
  { v: '3', l: 'Среда' },
  { v: '4', l: 'Четверг' },
  { v: '5', l: 'Пятница' },
  { v: '6', l: 'Суббота' },
  { v: '0', l: 'Воскресенье' },
] as const

function orDefault(value: string | null | undefined, fallback: string): string {
  const trimmed = (value ?? '').trim()
  return trimmed || fallback
}

export default function NocScheduleCard() {
  const { user, refreshUser } = useAuth()
  const { timeZone, effectiveTimeZone } = useTimezone()
  const { success, error: notifyError } = useNotifications()

  const [dailyTime, setDailyTime] = useState(DEFAULT_DAILY)
  const [weeklyDow, setWeeklyDow] = useState(DEFAULT_WEEKLY_DOW)
  const [weeklyTime, setWeeklyTime] = useState(DEFAULT_WEEKLY_TIME)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!user || user.role !== 'admin') return
    setDailyTime(orDefault(user.noc_daily_time, DEFAULT_DAILY))
    setWeeklyDow(orDefault(user.noc_weekly_dow, DEFAULT_WEEKLY_DOW))
    setWeeklyTime(orDefault(user.noc_weekly_time, DEFAULT_WEEKLY_TIME))
  }, [user])

  if (!user || user.role !== 'admin') return null

  const timezoneUnset = !timeZone.trim()

  const saveField = async (patch: {
    noc_daily_time?: string
    noc_weekly_dow?: string
    noc_weekly_time?: string
  }) => {
    setSaving(true)
    try {
      await updateSettings(patch)
      await refreshUser()
      success('Расписание NOC сохранено')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось сохранить расписание')
    } finally {
      setSaving(false)
    }
  }

  const handleDailyChange = (value: string) => {
    setDailyTime(value)
    void saveField({ noc_daily_time: value })
  }

  const handleWeeklyDowChange = (value: string) => {
    setWeeklyDow(value)
    // Persist both weekly fields together so personal weekly activates intentionally.
    void saveField({
      noc_weekly_dow: value,
      noc_weekly_time: orDefault(weeklyTime, DEFAULT_WEEKLY_TIME),
    })
  }

  const handleWeeklyTimeChange = (value: string) => {
    setWeeklyTime(value)
    void saveField({
      noc_weekly_dow: orDefault(weeklyDow, DEFAULT_WEEKLY_DOW),
      noc_weekly_time: value,
    })
  }

  return (
    <>
      <div className="md:col-span-2">
        <h3 className="text-sm font-semibold tracking-tight">NOC сводка</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Персональное время ежедневной и еженедельной сводки
        </p>
      </div>
      <Card className="overflow-hidden shadow-sm md:col-span-2">
        <div className="h-1 bg-gradient-to-r from-amber-500/70 to-amber-500/15" />
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <CalendarClock size={18} />
            NOC сводка — расписание
          </CardTitle>
          <CardDescription>
            Время по вашему часовому поясу ({effectiveTimeZone})
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {timezoneUnset ? (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-900 dark:text-amber-100">
              Часовой пояс профиля не задан (сейчас {effectiveTimeZone}). Укажите пояс в блоке
              «Часовой пояс» выше — иначе сводки могут приходить не в ожидаемое локальное время.
            </div>
          ) : null}

          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="noc-daily-time">Ежедневно</Label>
              <Input
                id="noc-daily-time"
                type="time"
                value={dailyTime}
                disabled={saving}
                onChange={(e) => handleDailyChange(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="noc-weekly-dow">День недели</Label>
              <Select value={weeklyDow} onValueChange={handleWeeklyDowChange} disabled={saving}>
                <SelectTrigger id="noc-weekly-dow">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DOW_OPTIONS.map((opt) => (
                    <SelectItem key={opt.v} value={opt.v}>
                      {opt.l}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="noc-weekly-time">Еженедельно</Label>
              <Input
                id="noc-weekly-time"
                type="time"
                value={weeklyTime}
                disabled={saving}
                onChange={(e) => handleWeeklyTimeChange(e.target.value)}
              />
            </div>
          </div>

          <p className="text-xs text-muted-foreground">
            Пока значения не сохранены, действует системное расписание. Ежедневное время
            сохраняется отдельно; персональное еженедельное включается при изменении дня или
            времени недели (сохраняются оба поля сразу).
          </p>
        </CardContent>
      </Card>
    </>
  )
}
