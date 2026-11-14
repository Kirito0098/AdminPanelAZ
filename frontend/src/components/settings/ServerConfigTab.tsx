import { useCallback, useEffect, useMemo, useState } from 'react'
import { ClipboardCheck, RefreshCw, Wrench } from 'lucide-react'
import { ApiError, applyServerConfig, getServerConfigPreview } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { SettingsToolbar } from '@/components/settings/SettingsChrome'
import {
  SettingsCard as Card,
  SettingsCardContent as CardContent,
  SettingsCardDescription as CardDescription,
  SettingsCardHeader as CardHeader,
  SettingsCardTitle as CardTitle,
} from '@/components/settings/SettingsCard'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import {
  NGINX_STEP_KEY,
  defaultStepSelection,
  hasNginxRisk,
  isSnippetIntegration,
  nginxRiskNotes,
  sanitizeStepSelection,
} from '@/lib/serverConfigSelection'
import type {
  NginxImpact,
  NginxStatusOpenVpn,
  NginxVhostImpact,
  ServerConfigDetail,
  ServerConfigPreview,
  ServerConfigRow,
  ServerConfigStep,
} from '@/types'

const STATUS_BADGE: Record<ServerConfigRow['status'], 'success' | 'secondary' | 'destructive'> = {
  ok: 'success',
  пропущен: 'secondary',
  ошибка: 'destructive',
}

const VHOST_ROLE_LABEL: Record<NginxVhostImpact['role'], string> = {
  panel: 'панель',
  portal: 'портал',
  other: 'другой сайт',
  statusopenvpn: 'СтатусOpenVPN',
}

const VHOST_ROLE_BADGE: Record<NginxVhostImpact['role'], 'default' | 'secondary' | 'outline' | 'warning'> = {
  panel: 'default',
  portal: 'secondary',
  other: 'outline',
  statusopenvpn: 'warning',
}

function DetailLines({ sign, lines, className }: { sign: string; lines: string[]; className: string }) {
  return lines.map((line) => (
    <div key={sign + line} className={className}>
      <span aria-hidden="true" className="select-none pr-2">
        {sign}
      </span>
      {line}
    </div>
  ))
}

function ItemDetail({ detail }: { detail: ServerConfigDetail }) {
  const diff = detail.removed.length + detail.added.length > 0
  return (
    <div className="mt-1.5 space-y-2">
      {diff ? (
        <div className="overflow-x-auto rounded-lg border bg-muted/40 px-3 py-2 font-mono text-xs leading-relaxed">
          <DetailLines sign="−" lines={detail.removed} className="whitespace-pre text-destructive" />
          <DetailLines sign="+" lines={detail.added} className="whitespace-pre text-emerald-600 dark:text-emerald-400" />
        </div>
      ) : null}
      {detail.info.length ? (
        <ul className="space-y-0.5 text-foreground/80">
          {detail.info.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}
      {detail.why.map((line) => (
        <p key={line}>
          <span className="font-medium text-foreground">Почему это важно: </span>
          {line}
        </p>
      ))}
    </div>
  )
}

function Section({ title, items, details = {} }: { title: string; items: string[]; details?: Record<string, ServerConfigDetail> }) {
  if (!items.length) return null
  return (
    <section className="space-y-1.5">
      <h4 className="text-sm font-semibold">{title}</h4>
      <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground marker:text-muted-foreground/60">
        {items.map((item) => (
          <li key={item}>
            {item}
            {details[item] ? <ItemDetail detail={details[item]} /> : null}
          </li>
        ))}
      </ul>
    </section>
  )
}

function VhostLine({ vhost, riskNote }: { vhost: NginxVhostImpact; riskNote?: string }) {
  return (
    <li className="space-y-0.5 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs">{vhost.host}</span>
        <Badge variant={VHOST_ROLE_BADGE[vhost.role]}>{VHOST_ROLE_LABEL[vhost.role]}</Badge>
        <span className="text-xs text-muted-foreground">
          {vhost.same_domain ? 'тот же домен' : 'другой домен/поддомен'}
        </span>
      </div>
      {vhost.note ? <p className="text-xs text-muted-foreground">{vhost.note}</p> : null}
      {riskNote ? <p className="text-xs font-medium text-destructive">{riskNote}</p> : null}
    </li>
  )
}

function StatusOpenVpnLine({ status }: { status: NginxStatusOpenVpn }) {
  if (status.outside_nginx) {
    return (
      <p className="text-sm text-muted-foreground">
        СтатусOpenVPN вне этого nginx — панель его не видит и не меняет.
        {status.detail ? ` ${status.detail}` : ''}
      </p>
    )
  }
  if (!status.in_nginx) return null
  return (
    <li className="space-y-0.5 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs">{status.domain || 'StatusOpenVPN'}</span>
        <Badge variant="warning">СтатусOpenVPN</Badge>
        <Badge variant="secondary">не меняется</Badge>
        {status.path ? <span className="font-mono text-xs text-muted-foreground">{status.path}</span> : null}
      </div>
      {status.detail ? <p className="text-xs text-muted-foreground">{status.detail}</p> : null}
    </li>
  )
}

function NginxImpactCard({ impact, nginxSelected }: { impact: NginxImpact; nginxSelected: boolean }) {
  const vhosts = impact.vhosts ?? []
  const foreign = impact.foreign_locations ?? []
  const globalChanges = impact.global_changes ?? []
  const warnings = impact.warnings ?? []
  const snippetMode = isSnippetIntegration(impact)
  const status = impact.status_openvpn
  const hasStatusVhost = vhosts.some((vhost) => vhost.role === 'statusopenvpn')
  const changing = nginxSelected ? vhosts.filter((vhost) => vhost.will_change) : []
  const kept = nginxSelected ? vhosts.filter((vhost) => !vhost.will_change) : vhosts
  const snippetRiskNote = snippetMode && nginxSelected
    ? 'Панель подключена сюда snippet\'ом — обновление nginx может перезаписать vhost вместе с настройками StatusOpenVPN.'
    : undefined
  const panelHost = impact.panel_vhost || impact.panel_domain

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <ClipboardCheck size={16} aria-hidden />
          </span>
          Влияние на nginx
        </CardTitle>
        <CardDescription>Что шаг nginx затронет, а что оставит как есть</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm text-muted-foreground">
        <div className="space-y-1">
          {panelHost ? (
            <p>
              Панель:{' '}
              <span className="font-mono text-xs text-foreground">{panelHost}</span>
              {snippetMode ? ' (snippet)' : ''}
            </p>
          ) : null}
          {snippetMode && impact.panel_snippet_includes?.length ? (
            <div>
              <p className="text-xs">Сниппеты панели:</p>
              <ul className="mt-1 space-y-0.5">
                {impact.panel_snippet_includes.map((include) => (
                  <li key={include} className="break-all font-mono text-xs text-foreground">
                    {include}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>

        {!impact.nginx_seen ? (
          <p className="rounded-lg border border-dashed border-border/80 px-3 py-3 text-sm text-muted-foreground">
            nginx не обнаружен или его конфигурация недоступна — панель не может оценить изменения.
          </p>
        ) : null}

        {warnings.length ? (
          <SettingsAlert variant="warning" title="Предупреждения nginx">
            <ul className="list-disc space-y-1 pl-4">
              {warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </SettingsAlert>
        ) : null}

        {changing.length || (nginxSelected && foreign.length) ? (
          <section className="space-y-1.5">
            <h4 className="text-sm font-semibold text-foreground">Изменится</h4>
            <ul className="space-y-2">
              {changing.map((vhost) => (
                <VhostLine key={`change-${vhost.host}`} vhost={vhost} riskNote={snippetRiskNote} />
              ))}
              {nginxSelected
                ? foreign.map((location) => (
                    <li key={`foreign-${location.path}`} className="space-y-0.5 text-sm">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs">{location.path}</span>
                        <Badge variant="destructive">чужой блок</Badge>
                        <span className="text-xs">проект: {location.project}</span>
                      </div>
                      {location.target ? (
                        <p className="break-all font-mono text-xs text-muted-foreground">{location.target}</p>
                      ) : null}
                    </li>
                  ))
                : null}
            </ul>
          </section>
        ) : null}

        {nginxSelected && !changing.length && !foreign.length ? (
          <p>Изменений в nginx нет.</p>
        ) : null}

        {!nginxSelected && !changing.length ? (
          <p>Nginx не выбран — его vhost'ы и общие файлы останутся как есть.</p>
        ) : null}

        {kept.length || (!hasStatusVhost && status?.in_nginx) ? (
          <section className="space-y-1.5">
            <h4 className="text-sm font-semibold text-foreground">Не изменится</h4>
            <ul className="space-y-2">
              {kept.map((vhost) => (
                <VhostLine
                  key={`keep-${vhost.host}`}
                  vhost={vhost}
                  riskNote={vhost.role === 'statusopenvpn' || vhost.host === impact.panel_vhost ? snippetRiskNote : undefined}
                />
              ))}
              {!hasStatusVhost && status?.in_nginx ? <StatusOpenVpnLine status={status} /> : null}
            </ul>
          </section>
        ) : null}

        {globalChanges.length ? (
          <section className="space-y-1.5">
            <h4 className="text-sm font-semibold text-foreground">Глобально</h4>
            <ul className="list-disc space-y-1 pl-5 marker:text-muted-foreground/60">
              {globalChanges.map((change) => (
                <li key={change}>{change}</li>
              ))}
            </ul>
            {!nginxSelected ? <p className="text-xs">Появится только если отметить nginx.</p> : null}
          </section>
        ) : null}

        {status?.outside_nginx ? <StatusOpenVpnLine status={status} /> : null}
      </CardContent>
    </Card>
  )
}

export default function ServerConfigTab() {
  const { success, error: notifyError } = useNotifications()
  const { trackBackgroundTask } = useProgress()
  const { confirm, dialogProps } = useConfirmDialog()
  const [preview, setPreview] = useState<ServerConfigPreview | null>(null)
  const [loadError, setLoadError] = useState('')
  const [loading, setLoading] = useState(true)
  const [applying, setApplying] = useState(false)
  const [rows, setRows] = useState<ServerConfigRow[]>([])
  const [selectedKeys, setSelectedKeys] = useState<string[] | null>(null)
  const [appliedSubset, setAppliedSubset] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError('')
    try {
      setPreview(await getServerConfigPreview())
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : 'Не удалось проверить сервер')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const steps = useMemo<ServerConfigStep[]>(() => preview?.steps ?? [], [preview])
  const defaults = useMemo(() => defaultStepSelection(preview), [preview])
  const selected = useMemo(
    () => sanitizeStepSelection(selectedKeys ?? defaults, steps),
    [selectedKeys, defaults, steps],
  )
  const selectedLabels = steps.filter((step) => selected.includes(step.key)).map((step) => step.label)
  const nginxSelected = selected.includes(NGINX_STEP_KEY)
  const impact = preview?.nginx_impact
  const nginxRisk = hasNginxRisk(impact)
  const riskNotes = nginxRiskNotes(impact)

  const finish = (resultRows: ServerConfigRow[], ok: boolean, message: string) => {
    setApplying(false)
    setRows(resultRows)
    if (ok) success(message)
    else notifyError(message)
    if (ok) setSelectedKeys(null)
    void load()
  }

  const toggleStep = (key: string, next: boolean) => {
    setSelectedKeys(next ? [...selected, key] : selected.filter((item) => item !== key))
  }

  const handleApply = () => {
    if (!selected.length) return
    const subset = steps.some((step) => step.available && !selected.includes(step.key))
    confirm({
      title: 'Обновить настройки сервера?',
      description: `Применятся только отмеченные шаги: ${selectedLabels.join(', ')}.`,
      alert:
        nginxSelected && riskNotes.length
          ? {
              variant: 'danger',
              title: 'Nginx может быть перезаписан',
              children: (
                <ul className="list-disc space-y-1 pl-4">
                  {riskNotes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              ),
            }
          : {
              variant: 'info',
              title: 'Панель продолжит работать',
              children: preview?.sections.effect.join('. ') || 'Панель и агенты не перезапускаются.',
            },
      confirmLabel: 'Применить',
      onConfirm: async () => {
        setApplying(true)
        setRows([])
        setAppliedSubset(subset)
        try {
          const resp = await applyServerConfig(selected)
          trackBackgroundTask(resp.task_id, {
            onComplete: (task) => {
              const result = task.result as { success?: boolean; message?: string; rows?: ServerConfigRow[] } | undefined
              finish(result?.rows ?? [], Boolean(result?.success), result?.message || 'Настройки сервера обновлены')
            },
            onError: (_task, message) => finish([], false, message || 'Не удалось обновить настройки сервера'),
          })
        } catch (err) {
          setApplying(false)
          notifyError(err instanceof ApiError ? err.message : 'Не удалось запустить обновление настроек')
        }
      },
    })
  }

  const pending = preview?.pending ?? 0
  const sections = preview?.sections

  return (
    <div className="space-y-4">
      <ConfirmDialogHost dialogProps={dialogProps} />
      <SettingsToolbar
        title="Настройки сервера"
        meta="То, что обновление через панель не меняет: nginx, системные пакеты, команда adminpanelaz, службы"
        actions={
          <>
            {preview && !loading ? (
              <Badge variant={pending ? 'warning' : 'success'}>{pending ? `Нужно обновить: ${pending}` : 'Всё актуально'}</Badge>
            ) : null}
            <Button variant="outline" size="sm" className="gap-2" onClick={() => void load()} disabled={loading || applying}>
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              Проверить снова
            </Button>
            {pending > 0 ? (
              <Button
                size="sm"
                className="gap-2"
                onClick={handleApply}
                disabled={loading || applying || selected.length === 0}
              >
                <Wrench size={14} />
                {applying ? 'Применяем…' : 'Применить'}
              </Button>
            ) : null}
          </>
        }
      />

      {appliedSubset && pending > 0 ? (
        <SettingsAlert variant="info" title="Применены не все шаги">
          Применены только отмеченные шаги; невыбранные изменения остались.
        </SettingsAlert>
      ) : null}

      {rows.length > 0 ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2.5">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <ClipboardCheck size={16} aria-hidden />
              </span>
              Итог применения
            </CardTitle>
            <CardDescription>Результат последнего запуска — шаг за шагом</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <ul className="space-y-1.5">
              {rows.map((row) => (
                <li key={row.step} className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="w-32 shrink-0 font-medium">{row.label}</span>
                  <Badge variant={STATUS_BADGE[row.status]}>{row.status}</Badge>
                  {row.detail ? <span className="min-w-0 text-muted-foreground">{row.detail}</span> : null}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {loading && !preview ? <Spinner label="Проверяем сервер..." className="py-10" /> : null}

      {loadError ? (
        <SettingsAlert variant="danger" title="Не удалось проверить сервер">
          {loadError}
        </SettingsAlert>
      ) : null}

      {preview && steps.length ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2.5">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Wrench size={16} aria-hidden />
              </span>
              Что обновить
            </CardTitle>
            <CardDescription>
              Отметьте шаги, которые нужно применить. Невыбранные изменения останутся как есть.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {nginxRisk ? (
              <SettingsAlert
                variant={nginxSelected ? 'danger' : 'warning'}
                title={nginxSelected ? 'Nginx выбран: риск активен' : 'Nginx не выбран по умолчанию'}
              >
                <ul className="list-disc space-y-1 pl-4">
                  {riskNotes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
                <p className="mt-2">
                  {nginxSelected
                    ? 'Снимите галочку nginx, если не готовы к перезаписи конфигурации.'
                    : 'Его файлы останутся как есть; включите вручную, если уверены в конфигурации.'}
                </p>
              </SettingsAlert>
            ) : null}

            <ul className="space-y-2">
              {steps.map((step) => (
                <li key={step.key}>
                  <label className="flex items-start gap-3 rounded-lg border border-border/70 bg-muted/15 p-3">
                    <Checkbox
                      checked={selected.includes(step.key)}
                      disabled={!step.available || applying}
                      onCheckedChange={(next) => toggleStep(step.key, next)}
                      aria-label={step.label}
                      className="mt-0.5"
                    />
                    <span className="min-w-0 space-y-0.5">
                      <span className="block text-sm font-medium">{step.label}</span>
                      {!step.available ? (
                        <span className="block text-xs text-muted-foreground">
                          {step.reason || 'Недоступно на этом сервере'}
                        </span>
                      ) : null}
                    </span>
                  </label>
                </li>
              ))}
            </ul>

            {selected.length === 0 ? (
              <p className="text-xs text-muted-foreground">Отметьте хотя бы один шаг, чтобы применить изменения.</p>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {impact ? <NginxImpactCard impact={impact} nginxSelected={nginxSelected} /> : null}

      {sections ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2.5">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Wrench size={16} aria-hidden />
              </span>
              План изменений
            </CardTitle>
            <CardDescription>Что добавится, изменится и останется как есть</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {pending === 0 ? (
              <p className="rounded-lg border border-dashed border-border/80 px-3 py-3 text-sm text-muted-foreground">
                Всё, что можно обновить отсюда, уже в актуальном состоянии.
              </p>
            ) : null}
            <Section title="Добавится" items={sections.add} />
            <Section
              title="Изменится"
              items={pending > 0 ? [...sections.change, ...sections.recheck] : []}
              details={preview.details}
            />
            <Section title="Не изменится" items={sections.keep} />
            {pending > 0 ? (
              <>
                <Section title="Удалится" items={sections.remove} />
                <Section title="Как это повлияет" items={sections.effect} />
              </>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
