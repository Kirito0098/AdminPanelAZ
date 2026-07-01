import { useEffect, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  ArrowUpCircle,
  CheckCircle2,
  Download,
  GitCommit,
  Package,
  RefreshCw,
  Rocket,
  Server,
  ShieldAlert,
  Sparkles,
} from 'lucide-react'
import { ApiError, applySystemUpdate, checkSystemUpdates, getLatestChangelog } from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import Spinner from '@/components/ui/Spinner'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { cn } from '@/lib/utils'
import type { ChangelogBlock, LatestChangelog } from '@/types'

const UPDATE_STEPS = [
  { icon: GitCommit, label: 'Загрузка кода', detail: 'git fetch и pull с GitHub' },
  { icon: Package, label: 'Зависимости', detail: 'pip install и npm install' },
  { icon: Rocket, label: 'Сборка UI', detail: 'npm run build:all' },
  { icon: Server, label: 'Перезапуск', detail: 'adminpanelaz через systemd' },
] as const

function shortHash(hash?: string) {
  if (!hash) return '—'
  return hash.length > 10 ? hash.slice(0, 10) : hash
}

function MetricPill({
  icon: Icon,
  label,
  value,
  tone = 'default',
}: {
  icon: LucideIcon
  label: string
  value: string
  tone?: 'default' | 'success' | 'muted' | 'warning'
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-card/80 p-3 shadow-sm backdrop-blur-sm">
      <div
        className={cn(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl',
          tone === 'success' && 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
          tone === 'warning' && 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
          tone === 'muted' && 'bg-muted text-muted-foreground',
          tone === 'default' && 'bg-muted/80 text-foreground',
        )}
      >
        <Icon size={18} />
      </div>
      <div className="min-w-0">
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="truncate font-mono text-sm font-semibold">{value}</p>
      </div>
    </div>
  )
}

function UpdatePipeline() {
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {UPDATE_STEPS.map((step, index) => (
        <div
          key={step.label}
          className="relative flex items-start gap-3 rounded-xl border bg-card/60 p-3 transition-colors hover:bg-muted/30"
        >
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <step.icon size={16} />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-medium text-muted-foreground">Шаг {index + 1}</p>
            <p className="text-sm font-semibold leading-tight">{step.label}</p>
            <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{step.detail}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

function formatVersionLabel(version: string) {
  return version.toLowerCase() === 'unreleased' ? 'В разработке' : `v${version}`
}

function changelogItemCount(block: ChangelogBlock) {
  return (block.sections ?? []).reduce((sum, section) => sum + section.items.length, 0)
}

function ChangelogPanel({
  block,
  title,
  subtitle,
  badge,
  accent = 'default',
}: {
  block: ChangelogBlock
  title: string
  subtitle?: string
  badge?: string
  accent?: 'default' | 'available' | 'pending'
}) {
  const sections = block.sections ?? []
  const itemCount = changelogItemCount(block)
  if (sections.length === 0) return null

  return (
    <div
      className={cn(
        'overflow-hidden rounded-2xl border shadow-sm',
        accent === 'available' && 'border-primary/30 bg-gradient-to-b from-primary/5 via-card to-card',
        accent === 'pending' && 'border-amber-500/30 bg-gradient-to-b from-amber-500/5 via-card to-card',
        accent === 'default' && 'border-border/80 bg-gradient-to-b from-card to-muted/15',
      )}
    >
      <div
        className={cn(
          'border-b px-5 py-5 sm:px-6',
          accent === 'available' && 'bg-primary/5',
          accent === 'pending' && 'bg-amber-500/5',
          accent === 'default' && 'bg-muted/25',
        )}
      >
        <div className="flex flex-wrap items-center gap-2.5">
          <span
            className={cn(
              'inline-flex items-center gap-2 rounded-full px-3 py-1 font-mono text-sm font-bold',
              accent === 'available' && 'bg-primary text-primary-foreground',
              accent === 'pending' && 'bg-amber-500/20 text-amber-800 dark:text-amber-200',
              accent === 'default' && 'bg-primary/15 text-primary',
            )}
          >
            <Sparkles size={14} />
            {formatVersionLabel(block.version)}
          </span>
          {block.date && <span className="text-sm text-muted-foreground">{block.date}</span>}
          <Badge variant="outline" className="text-xs">
            {itemCount} {itemCount === 1 ? 'пункт' : itemCount < 5 ? 'пункта' : 'пунктов'}
          </Badge>
          {badge && (
            <Badge variant={accent === 'available' ? 'warning' : 'secondary'} className="text-xs">
              {badge}
            </Badge>
          )}
        </div>
        <h4 className="mt-3 text-lg font-semibold tracking-tight">{title}</h4>
        {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
      </div>

      <div className="min-h-[28rem] max-h-[min(75vh,52rem)] overflow-y-auto px-5 py-5 sm:px-6">
        <div className="space-y-8">
          {sections.map((section) => (
            <section key={section.title} className="border-b border-border/50 pb-8 last:border-b-0 last:pb-0">
              <h5 className="text-base font-semibold tracking-tight text-foreground">{section.title}</h5>
              <ul className="mt-4 space-y-4">
                {section.items.map((item) => (
                  <li key={item} className="flex gap-3 text-[15px] leading-7 text-muted-foreground sm:text-base sm:leading-8">
                    <span className="mt-2.5 h-2 w-2 shrink-0 rounded-full bg-primary/70" />
                    <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">{item}</span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function UpdatesTab() {
  const { success, error: notifyError } = useNotifications()
  const { trackBackgroundTask } = useProgress()
  const { confirm, dialogProps } = useConfirmDialog()
  const [info, setInfo] = useState<{
    updates_available?: boolean
    commits_behind?: number
    local_hash?: string
    remote_hash?: string
    error?: string
  } | null>(null)
  const [changelog, setChangelog] = useState<LatestChangelog | null>(null)
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const [updates, changelogResp] = await Promise.all([
        checkSystemUpdates(),
        getLatestChangelog().catch(() => null),
      ])
      setInfo(updates)
      setChangelog(changelogResp)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка проверки обновлений')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleUpdate = () => {
    confirm({
      title: 'Применить обновление?',
      description: 'Загрузит новую версию панели, обновит зависимости и перезапустит сервис.',
      alert: {
        variant: 'warning',
        title: 'Перед обновлением',
        children: 'Рекомендуется создать бэкап. Панель перезапустится автоматически через несколько секунд после сборки.',
      },
      confirmLabel: 'Применить обновление',
      destructive: true,
      onConfirm: async () => {
        setUpdating(true)
        try {
          const resp = await applySystemUpdate()
          trackBackgroundTask(resp.task_id, {
            onComplete: () => {
              success(resp.message || 'Обновление применено')
              void load()
            },
            onError: (task, message) => {
              notifyError(task?.error || task?.message || message)
            },
          })
        } catch (err) {
          notifyError(err instanceof ApiError ? err.message : 'Ошибка обновления')
        } finally {
          setUpdating(false)
        }
      },
    })
  }

  if (loading && !info) {
    return <Spinner label="Проверка обновлений..." className="py-12" />
  }

  const hasUpdate = Boolean(info?.updates_available)
  const commitsBehind = info?.commits_behind ?? 0
  const latestRelease = changelog?.latest_release
  const pendingRelease = changelog?.pending
  const showPendingUnreleased =
    hasUpdate &&
    pendingRelease?.sections?.length &&
    pendingRelease.version.toLowerCase() === 'unreleased'
  const changelogSourceLabel =
    changelog?.source === 'git' ? 'с origin/main на GitHub' : 'с GitHub (raw)'

  return (
    <div className="space-y-4">
      <ConfirmDialogHost dialogProps={dialogProps} />
      <InlineProgressBar active={updating} label="Применение обновления..." />

      {/* Status hero */}
      <div
        className={cn(
          'relative overflow-hidden rounded-xl border p-5',
          hasUpdate
            ? 'border-primary/30 bg-gradient-to-br from-primary/10 via-card to-amber-500/5'
            : info?.error
              ? 'border-destructive/30 bg-gradient-to-br from-destructive/5 via-card to-card'
              : 'border-emerald-500/20 bg-gradient-to-br from-emerald-500/10 via-card to-card',
        )}
      >
        <div
          className={cn(
            'pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full blur-3xl',
            hasUpdate ? 'bg-primary/20' : info?.error ? 'bg-destructive/10' : 'bg-emerald-500/15',
          )}
        />
        <div className="relative flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-4">
            <div
              className={cn(
                'flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl shadow-sm',
                hasUpdate
                  ? 'bg-primary/15 text-primary'
                  : info?.error
                    ? 'bg-destructive/15 text-destructive'
                    : 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
              )}
            >
              {hasUpdate ? (
                <ArrowUpCircle size={28} />
              ) : info?.error ? (
                <ShieldAlert size={28} />
              ) : (
                <CheckCircle2 size={28} />
              )}
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-lg font-semibold tracking-tight">
                  {hasUpdate
                    ? 'Доступно обновление'
                    : info?.error
                      ? 'Не удалось проверить'
                      : 'Панель актуальна'}
                </h3>
                {hasUpdate ? (
                  <Badge variant="warning">
                    +{commitsBehind} {commitsBehind === 1 ? 'коммит' : commitsBehind < 5 ? 'коммита' : 'коммитов'}
                  </Badge>
                ) : !info?.error ? (
                  <Badge variant="success">Последняя версия</Badge>
                ) : null}
              </div>
              <p className="mt-1 max-w-xl text-sm text-muted-foreground">
                {hasUpdate
                  ? 'Новая версия готова к установке. Процесс займёт несколько минут и завершится перезапуском панели.'
                  : info?.error
                    ? 'Проверьте подключение к GitHub и доступ к репозиторию на сервере.'
                    : 'Установлена последняя версия с сервера разработчиков. Проверяйте обновления периодически.'}
              </p>
            </div>
          </div>
          <Button
            variant="outline"
            className="shrink-0 gap-2 bg-card/80 backdrop-blur-sm"
            onClick={load}
            disabled={loading || updating}
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            {loading ? 'Проверка...' : 'Проверить снова'}
          </Button>
        </div>
      </div>

      {/* Version metrics */}
      {info && (
        <div className="grid gap-3 sm:grid-cols-3">
          <MetricPill
            icon={GitCommit}
            label="Установлено"
            value={shortHash(info.local_hash)}
            tone={hasUpdate ? 'muted' : 'success'}
          />
          <MetricPill
            icon={Download}
            label="На сервере"
            value={shortHash(info.remote_hash)}
            tone={hasUpdate ? 'warning' : 'muted'}
          />
          <MetricPill
            icon={ArrowUpCircle}
            label="Отставание"
            value={hasUpdate ? `${commitsBehind} комм.` : 'Нет'}
            tone={hasUpdate ? 'warning' : 'success'}
          />
        </div>
      )}

      {info?.error && (
        <SettingsAlert variant="danger" title="Ошибка проверки">
          {info.error}
        </SettingsAlert>
      )}

      {changelog && !changelog.success && changelog.message && (
        <SettingsAlert variant="info" title="Changelog недоступен">
          {changelog.message}
        </SettingsAlert>
      )}

      {latestRelease?.sections?.length ? (
        <ChangelogPanel
          block={latestRelease}
          title={hasUpdate ? 'Что нового в доступной версии' : 'Состав последнего обновления'}
          subtitle={`Данные загружены ${changelogSourceLabel}`}
          badge={hasUpdate ? 'Доступно для установки' : 'Текущая версия'}
          accent={hasUpdate ? 'available' : 'default'}
        />
      ) : null}

      {showPendingUnreleased && pendingRelease ? (
        <ChangelogPanel
          block={pendingRelease}
          title="Дополнительные изменения в разработке"
          subtitle="Попадут в установку вместе с обновлением"
          accent="pending"
        />
      ) : null}

      {hasUpdate ? (
        <>
          <Card className="relative overflow-hidden border-primary/20 shadow-sm">
            <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-primary/60 to-amber-500/40" />
            <CardHeader className="pb-3">
              <div className="flex items-start gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary">
                  <Rocket size={20} />
                </div>
                <div>
                  <CardTitle className="text-base">Установить обновление</CardTitle>
                  <CardDescription className="mt-1">
                    Выполнит полный цикл обновления и перезапустит панель автоматически
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <UpdatePipeline />
              <SettingsAlert variant="warning" title="Перед обновлением">
                Рекомендуется создать резервную копию в разделе «Резервные копии». Панель ненадолго
                перезапустится — дождитесь завершения процесса.
              </SettingsAlert>
              <div className="flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs text-muted-foreground">
                  Прогресс отображается в строке состояния вверху страницы
                </p>
                <Button
                  variant="destructive"
                  size="lg"
                  className="gap-2 sm:shrink-0"
                  onClick={handleUpdate}
                  disabled={updating}
                >
                  <Download size={18} />
                  {updating ? 'Обновление...' : 'Применить обновление'}
                </Button>
              </div>
            </CardContent>
          </Card>
        </>
      ) : !info?.error && info ? (
        !latestRelease?.sections?.length ? (
          <Card className="overflow-hidden border-emerald-500/20 shadow-sm">
            <div className="h-1 bg-gradient-to-r from-emerald-500/80 to-emerald-500/20" />
            <CardContent className="flex flex-col items-center gap-3 py-10 text-center sm:py-12">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 size={32} />
              </div>
              <div>
                <p className="text-base font-semibold">Всё в порядке</p>
                <p className="mt-1 max-w-md text-sm text-muted-foreground">
                  Версия{' '}
                  <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{shortHash(info.local_hash)}</code>{' '}
                  совпадает с актуальной на GitHub. Новых обновлений нет.
                </p>
              </div>
            </CardContent>
          </Card>
        ) : null
      ) : null}
    </div>
  )
}
