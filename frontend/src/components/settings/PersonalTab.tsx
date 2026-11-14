import { FormEvent, useState } from 'react'
import { Clock, KeyRound, Moon, Palette, Save, Send, Sun } from 'lucide-react'
import TwoFactorTab from '@/components/settings/TwoFactorTab'
import PasskeysTab from '@/components/settings/PasskeysTab'
import PersonalTelegramCard from '@/components/settings/PersonalTelegramCard'
import NocScheduleCard from '@/components/settings/NocScheduleCard'
import { SettingsCollapsible, SettingsPanel } from '@/components/settings/SettingsChrome'
import {
  SettingsCard as Card,
  SettingsCardContent as CardContent,
  SettingsCardDescription as CardDescription,
  SettingsCardHeader as CardHeader,
  SettingsCardTitle as CardTitle,
} from '@/components/settings/SettingsCard'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useAuth } from '@/context/AuthContext'
import { useFeatureModules } from '@/context/FeatureModulesContext'
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

const THEME_OPTIONS = [
  {
    value: 'light' as const,
    label: 'Светлая',
    hint: 'Классический светлый интерфейс',
    icon: Sun,
    preview: 'from-slate-50 to-slate-200',
    bar: 'bg-slate-300',
    dot: 'bg-primary',
  },
  {
    value: 'dark' as const,
    label: 'Тёмная',
    hint: 'Комфортная работа в тёмном режиме',
    icon: Moon,
    preview: 'from-slate-900 to-slate-950',
    bar: 'bg-slate-700',
    dot: 'bg-primary',
  },
] as const

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
  const { isEnabled } = useFeatureModules()
  const { user } = useAuth()
  const [extrasOpen, setExtrasOpen] = useState(false)
  const now = new Date()

  const showTelegramCard = isEnabled('telegram') && Boolean(user)
  const showNocCard = user?.role === 'admin'
  const showExtras = showTelegramCard || showNocCard

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2 md:items-stretch">
        <Card className="flex h-full flex-col">
          <CardHeader>
            <div className="flex items-start gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Palette size={16} aria-hidden />
              </span>
              <div className="min-w-0">
                <CardTitle>Внешний вид</CardTitle>
                <CardDescription className="mt-0.5">
                  Выберите тему интерфейса панели
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col">
            <div className="grid grid-cols-1 flex-1 gap-3 sm:grid-cols-2">
              {THEME_OPTIONS.map(({ value, label, hint, icon: Icon, preview, bar, dot }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => onThemeChange(value)}
                  className={cn(
                    'flex h-full flex-col gap-3 rounded-lg border p-3 text-left transition-all',
                    theme === value
                      ? 'border-primary/40 bg-primary/5 ring-1 ring-primary/30'
                      : 'border-border/70 bg-muted/10 hover:border-muted-foreground/30 hover:bg-muted/30',
                  )}
                >
                  <div
                    className={cn(
                      'relative min-h-[4.5rem] flex-1 overflow-hidden rounded-lg border border-border/60 bg-gradient-to-br',
                      preview,
                    )}
                  >
                    <div className={cn('absolute left-2 top-2 h-1.5 w-8 rounded-full', bar)} />
                    <div className={cn('absolute left-2 top-5 h-1 w-12 rounded-full opacity-60', bar)} />
                    <div className={cn('absolute bottom-2 right-2 h-2.5 w-2.5 rounded-full', dot)} />
                  </div>
                  <div className="flex items-center gap-2">
                    <div
                      className={cn(
                        'flex h-8 w-8 items-center justify-center rounded-lg',
                        theme === value ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground',
                      )}
                    >
                      <Icon size={16} />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{label}</p>
                      <p className="text-[11px] leading-snug text-muted-foreground">{hint}</p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="flex h-full flex-col">
          <CardHeader>
            <div className="flex items-start gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Clock size={16} aria-hidden />
              </span>
              <div className="min-w-0">
                <CardTitle>Часовой пояс</CardTitle>
                <CardDescription className="mt-0.5">
                  Дата и время в панели и в Telegram-оповещениях
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col justify-between gap-4">
            <div className="rounded-lg border border-border/70 bg-muted/20 px-4 py-3">
              <p className="text-xl font-semibold tabular-nums tracking-tight">
                {now.toLocaleTimeString('ru-RU', { timeZone: effectiveTimeZone, hour: '2-digit', minute: '2-digit' })}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">{formatDateTime(now)}</p>
              <p className="mt-1.5 inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium tabular-nums text-primary">
                {effectiveTimeZone}
              </p>
            </div>
            <div className="space-y-2">
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
          </CardContent>
        </Card>
      </div>

      <SettingsPanel>
        <div className="mb-4 flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <KeyRound size={16} aria-hidden />
          </span>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold tracking-tight">Смена пароля</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Обновите пароль для вашей учётной записи
            </p>
          </div>
        </div>
        <form noValidate onSubmit={onChangePassword} className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2 md:items-stretch">
            <div className="flex flex-col space-y-2 rounded-lg border border-border/70 bg-muted/20 p-3 sm:p-4">
              <Label htmlFor="currentPwd">Текущий пароль</Label>
              <Input
                id="currentPwd"
                type="password"
                value={currentPwd}
                onChange={(e) => onCurrentPwdChange(e.target.value)}
                autoComplete="current-password"
                className="w-full"
              />
            </div>
            <div className="flex flex-col space-y-2 rounded-lg border border-border/70 bg-muted/20 p-3 sm:p-4">
              <Label htmlFor="newPwd">Новый пароль</Label>
              <Input
                id="newPwd"
                type="password"
                value={newPwd}
                onChange={(e) => onNewPwdChange(e.target.value)}
                autoComplete="new-password"
                className="w-full"
              />
            </div>
          </div>
          <div className="flex flex-col-reverse gap-3 border-t border-border/70 pt-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-muted-foreground">Минимум 8 символов, буквы и цифры</p>
            <Button type="submit" className="w-full gap-1.5 sm:w-auto sm:shrink-0">
              <Save size={16} />
              Сохранить пароль
            </Button>
          </div>
        </form>
      </SettingsPanel>

      <div className="grid gap-4 md:grid-cols-2 md:items-stretch">
        <TwoFactorTab className="h-full" />
        <PasskeysTab className="h-full" />
      </div>

      {showExtras ? (
        <SettingsCollapsible
          open={extrasOpen}
          onOpenChange={setExtrasOpen}
          title="Telegram и NOC-сводка"
          description="Привязка Telegram-аккаунта и персональное расписание сводок"
          icon={<Send size={16} />}
        >
          {showTelegramCard ? <PersonalTelegramCard /> : null}
          {showNocCard ? <NocScheduleCard /> : null}
        </SettingsCollapsible>
      ) : null}
    </div>
  )
}
