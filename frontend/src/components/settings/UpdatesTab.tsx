import { useEffect, useState } from 'react'
import {
  CheckCircle2,
  Download,
  GitCommit,
  Package,
  RefreshCw,
  Rocket,
  Server,
  Sparkles,
} from 'lucide-react'
import { ApiError, applySystemUpdate, checkSystemUpdates, getLatestChangelog } from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { SettingsCollapsible, SettingsMetaLine, SettingsPanel, SettingsToolbar } from '@/components/settings/SettingsChrome'
import {
  UPDATE_CONFIRM_DURATION_NOTICE,
  UPDATE_LONG_RUNNING_NOTICE,
  UPDATE_POLL_BUSY_ALERT_BODY,
  UPDATE_POLL_BUSY_ALERT_TITLE,
  isLikelyBuildBusyPollError,
  resolveUpdateTaskErrorMessage,
} from '@/components/settings/updateGuidance'
import Spinner from '@/components/ui/Spinner'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
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

function UpdatePipeline() {
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {UPDATE_STEPS.map((step, index) => (
        <div key={step.label} className="flex items-start gap-3 rounded-lg border bg-muted/15 p-3">
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

function ChangelogSections({ block }: { block: ChangelogBlock }) {
  const sections = block.sections ?? []
  if (sections.length === 0) return null
  return (
    <div className="space-y-4">
      {sections.map((section) => (
        <section key={section.title}>
          <h5 className="text-sm font-medium tracking-tight">{section.title}</h5>
          <ul className="mt-2 space-y-1.5">
            {section.items.map((item) => (
              <li key={item} className="flex gap-2 text-sm text-muted-foreground">
                <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-primary/70" />
                <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">{item}</span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

export default function UpdatesTab() {
  const { success, error: notifyError, warning: notifyWarning } = useNotifications()
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
  const [changelogOpen, setChangelogOpen] = useState(false)
  const [pendingChangelogOpen, setPendingChangelogOpen] = useState(false)

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
        children: (
          <>
            Рекомендуется создать бэкап. Панель перезапустится автоматически через несколько секунд после сборки.
            <br />
            <br />
            {UPDATE_CONFIRM_DURATION_NOTICE}
          </>
        ),
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
              const resolved = resolveUpdateTaskErrorMessage(message, task)
              if (isLikelyBuildBusyPollError(message, task)) {
                notifyWarning(resolved)
                return
              }
              notifyError(resolved)
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
  const statusBadge = hasUpdate
    ? { variant: 'warning' as const, label: 'Доступно обновление' }
    : info?.error
      ? { variant: 'destructive' as const, label: 'Ошибка проверки' }
      : { variant: 'success' as const, label: 'Актуальная версия' }
  const statusDescription = hasUpdate
    ? 'Новая версия готова к установке. Процесс может занять до 15–20 минут и завершится перезапуском панели.'
    : info?.error
      ? 'Проверьте подключение к GitHub и доступ к репозиторию на сервере.'
      : 'Установлена последняя версия с сервера разработчиков. Проверяйте обновления периодически.'

  return (
    <div className="space-y-4">
      <ConfirmDialogHost dialogProps={dialogProps} />
      <InlineProgressBar active={updating} label="Применение обновления..." />

      <SettingsToolbar
        title="Обновления панели"
        meta={
          info ? (
            <SettingsMetaLine
              items={[
                { label: 'установлено', value: shortHash(info.local_hash) },
                { label: 'на сервере', value: shortHash(info.remote_hash) },
                ...(hasUpdate ? [{ label: 'отставание', value: `${commitsBehind} комм.` }] : []),
              ]}
            />
          ) : undefined
        }
        actions={
          <>
            <Badge variant={statusBadge.variant}>{statusBadge.label}</Badge>
            <Button
              variant="outline"
              size="sm"
              className="shrink-0 gap-2"
              onClick={load}
              disabled={loading || updating}
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              {loading ? 'Проверка...' : 'Проверить снова'}
            </Button>
          </>
        }
      />

      <p className="text-sm text-muted-foreground">{statusDescription}</p>

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
        <SettingsCollapsible
          open={changelogOpen}
          onOpenChange={setChangelogOpen}
          title={`${hasUpdate ? 'Что нового в доступной версии' : 'Состав последнего обновления'} — ${formatVersionLabel(latestRelease.version)}`}
          description={`${changelogItemCount(latestRelease)} пункт(ов) · данные загружены ${changelogSourceLabel}`}
          icon={<Sparkles size={16} />}
        >
          <ChangelogSections block={latestRelease} />
        </SettingsCollapsible>
      ) : null}

      {showPendingUnreleased && pendingRelease ? (
        <SettingsCollapsible
          open={pendingChangelogOpen}
          onOpenChange={setPendingChangelogOpen}
          title="Дополнительные изменения в разработке"
          description="Попадут в установку вместе с обновлением"
          icon={<Sparkles size={16} />}
        >
          <ChangelogSections block={pendingRelease} />
        </SettingsCollapsible>
      ) : null}

      {hasUpdate ? (
        <Card className="shadow-sm">
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
            <SettingsAlert variant="info" title="Длительность обновления">
              {UPDATE_LONG_RUNNING_NOTICE}
            </SettingsAlert>
            <SettingsAlert variant="info" title={UPDATE_POLL_BUSY_ALERT_TITLE}>
              {UPDATE_POLL_BUSY_ALERT_BODY}
            </SettingsAlert>
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
      ) : !info?.error && info ? (
        !latestRelease?.sections?.length ? (
          <SettingsPanel>
            <div className="flex flex-col items-center gap-3 py-6 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <CheckCircle2 size={24} />
              </div>
              <div>
                <p className="text-sm font-semibold">Всё в порядке</p>
                <p className="mt-1 max-w-md text-sm text-muted-foreground">
                  Версия{' '}
                  <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{shortHash(info.local_hash)}</code>{' '}
                  совпадает с актуальной на GitHub. Новых обновлений нет.
                </p>
              </div>
            </div>
          </SettingsPanel>
        ) : null
      ) : null}
    </div>
  )
}
