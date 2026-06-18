import { FormEvent } from 'react'
import { Clock, KeyRound, Moon, Palette, Sun } from 'lucide-react'
import TwoFactorTab from '@/components/settings/TwoFactorTab'
import PasskeysTab from '@/components/settings/PasskeysTab'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useTimezone } from '@/context/TimezoneContext'
import { formatDateTime, getTimeZoneLabel } from '@/lib/datetime'
import { cn } from '@/lib/utils'

const AUTO_TZ = '__auto__'

interface PersonalTabProps {
  theme: 'light' | 'dark'
  onThemeChange: (theme: 'light' | 'dark') => void
  currentPwd: string
  newPwd: string
  onCurrentPwdChange: (value: string) => void
  onNewPwdChange: (value: string) => void
  onChangePassword: (e: FormEvent) => void
}

export default function PersonalTab({
  theme,
  onThemeChange,
  currentPwd,
  newPwd,
  onCurrentPwdChange,
  onNewPwdChange,
  onChangePassword,
}: PersonalTabProps) {
  const { timeZone, effectiveTimeZone, browserTimeZone, options, setTimeZone } = useTimezone()
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Palette size={18} />
            Внешний вид
          </CardTitle>
          <CardDescription>Выберите тему интерфейса панели</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            {(
              [
                { value: 'light' as const, label: 'Светлая', icon: Sun },
                { value: 'dark' as const, label: 'Тёмная', icon: Moon },
              ] as const
            ).map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                type="button"
                onClick={() => onThemeChange(value)}
                className={cn(
                  'flex items-center gap-3 rounded-lg border p-4 text-left transition-colors',
                  theme === value
                    ? 'border-primary bg-primary/5 ring-1 ring-primary'
                    : 'hover:border-muted-foreground/30 hover:bg-muted/50',
                )}
              >
                <div
                  className={cn(
                    'flex h-10 w-10 items-center justify-center rounded-md',
                    theme === value ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground',
                  )}
                >
                  <Icon size={20} />
                </div>
                <div>
                  <p className="font-medium">{label}</p>
                  <p className="text-xs text-muted-foreground">
                    {value === 'light' ? 'Классический светлый интерфейс' : 'Комфортная работа в тёмном режиме'}
                  </p>
                </div>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Clock size={18} />
            Часовой пояс
          </CardTitle>
          <CardDescription>
            Дата и время во всей панели будут отображаться в выбранном часовом поясе
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid max-w-md gap-2">
            <Label htmlFor="timezone-select">Часовой пояс</Label>
            <Select
              value={timeZone || AUTO_TZ}
              onValueChange={(value) => setTimeZone(value === AUTO_TZ ? '' : value)}
            >
              <SelectTrigger id="timezone-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={AUTO_TZ}>
                  Как в браузере ({browserTimeZone} · {getTimeZoneLabel(browserTimeZone)})
                </SelectItem>
                {options.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <p className="text-xs text-muted-foreground">
            Текущее время: {formatDateTime(new Date())} · {effectiveTimeZone}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound size={18} />
            Смена пароля
          </CardTitle>
          <CardDescription>Обновите пароль для вашей учётной записи</CardDescription>
        </CardHeader>
        <CardContent>
          <form noValidate onSubmit={onChangePassword} className="grid max-w-md gap-4">
            <div className="space-y-2">
              <Label htmlFor="currentPwd">Текущий пароль</Label>
              <Input
                id="currentPwd"
                type="password"
                value={currentPwd}
                onChange={(e) => onCurrentPwdChange(e.target.value)}
                autoComplete="current-password"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="newPwd">Новый пароль</Label>
              <Input
                id="newPwd"
                type="password"
                value={newPwd}
                onChange={(e) => onNewPwdChange(e.target.value)}
                autoComplete="new-password"
              />
              <p className="text-xs text-muted-foreground">Минимум 4 символа</p>
            </div>
            <Button type="submit" className="w-fit">
              Сохранить пароль
            </Button>
          </form>
        </CardContent>
      </Card>

      <TwoFactorTab />
      <PasskeysTab />
    </div>
  )
}
