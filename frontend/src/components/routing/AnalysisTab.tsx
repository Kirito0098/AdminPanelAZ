import { useMemo, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  FlaskConical,
  Info,
  Loader2,
  ShieldAlert,
  Sparkles,
} from 'lucide-react'
import { analyzeDpiLog } from '@/api/client'
import MetricCard from '@/components/noc/MetricCard'
import StatusPanel from '@/components/noc/StatusPanel'
import ResponsiveDataView from '@/components/shared/ResponsiveDataView'
import type { RoutingTab } from '@/components/routing/routingWorkflow'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import type {
  CidrProviderInfo,
  DpiAnalysisNode,
  DpiAnalysisRecommendation,
  DpiAnalysisResult,
  DpiAnalysisTriggerNode,
} from '@/types'
import { formatCompactCount, providerCategoryLabel } from './utils'

const DPI_CHECKER_URL = 'https://hyperion-cs.github.io/dpi-checkers/ru/tcp-16-20/'

const LEVEL_META: Record<
  DpiAnalysisRecommendation['level'],
  { title: string; tone: string; icon: typeof ShieldAlert }
> = {
  must: {
    title: 'Включить обязательно',
    tone: 'border-red-500/40 bg-red-500/5',
    icon: ShieldAlert,
  },
  should: {
    title: 'Рекомендуется включить',
    tone: 'border-amber-500/40 bg-amber-500/5',
    icon: AlertTriangle,
  },
  consider: {
    title: 'Слабый сигнал',
    tone: 'border-yellow-500/30 bg-yellow-500/5',
    icon: Sparkles,
  },
  skip: {
    title: 'Можно не включать',
    tone: 'border-emerald-500/30 bg-emerald-500/5',
    icon: CheckCircle2,
  },
}

const CONFIDENCE_META: Record<
  DpiAnalysisRecommendation['confidence'],
  { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }
> = {
  high: { label: 'высокая уверенность', variant: 'destructive' },
  medium: { label: 'средняя уверенность', variant: 'secondary' },
  low: { label: 'низкая уверенность', variant: 'outline' },
  weak: { label: 'противоречивый результат', variant: 'outline' },
  inconclusive: { label: 'неоднозначно', variant: 'outline' },
}

const SEVERITY_META: Record<
  string,
  { label: string; badge: 'destructive' | 'secondary' | 'outline' | 'default' }
> = {
  detected: { label: 'detected', badge: 'destructive' },
  possible_detected: { label: 'possible', badge: 'secondary' },
  unlikely: { label: 'unlikely', badge: 'outline' },
  not_detected: { label: 'not detected', badge: 'default' },
  unknown: { label: 'unknown', badge: 'outline' },
}

const ALIVE_LABELS: Record<string, string> = {
  yes: 'alive: yes',
  no: 'alive: no',
  unknown: 'alive: unknown',
}

interface AnalysisTabProps {
  providers: CidrProviderInfo[]
  onNavigateTab?: (tab: RoutingTab) => void
}

function hostUrl(host?: string | null) {
  if (!host) return null
  return `https://${host}/`
}

function NodeChip({ node }: { node: DpiAnalysisTriggerNode }) {
  const severity = SEVERITY_META[node.severity] ?? SEVERITY_META.unknown
  const url = hostUrl(node.host)

  return (
    <div className="rounded-md border bg-background/80 px-2.5 py-2 text-xs">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="font-mono font-medium">{node.node_id}</span>
        <Badge variant={severity.badge} className="text-[10px]">
          {severity.label}
        </Badge>
        {node.dpi_method != null && (
          <Badge variant="outline" className="text-[10px]">
            method {node.dpi_method}
          </Badge>
        )}
        {node.alive && (
          <Badge variant="outline" className="text-[10px]">
            {ALIVE_LABELS[node.alive] ?? node.alive}
          </Badge>
        )}
      </div>
      {node.host && (
        <div className="mt-1 flex flex-wrap items-center gap-1 text-muted-foreground">
          <span className="font-mono">{node.host}</span>
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-0.5 text-primary hover:underline"
            >
              открыть
              <ExternalLink size={10} />
            </a>
          )}
        </div>
      )}
      {node.status_text && (
        <div className="mt-1 text-[11px] text-muted-foreground">{node.status_text}</div>
      )}
    </div>
  )
}

function DpiLogNodeCard({
  node,
  provider,
  providerName,
  routeLabel,
}: {
  node: DpiAnalysisNode
  provider?: CidrProviderInfo
  providerName: string
  routeLabel: string
}) {
  const severity = SEVERITY_META[node.severity] ?? SEVERITY_META.unknown
  const url = hostUrl(node.host)

  return (
    <Card className="p-4">
      <div className="font-mono text-xs font-medium">{node.node_id}</div>
      <dl className="mt-3 grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
        <div>
          <dt className="text-muted-foreground">Хост checker</dt>
          <dd className="mt-0.5">
            {node.host ? (
              <>
                <a
                  href={url ?? '#'}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="break-all font-mono text-primary hover:underline"
                >
                  {node.host}
                </a>
                {node.checker_country && (
                  <div className="text-[11px] text-muted-foreground">{node.checker_country}</div>
                )}
              </>
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">CIDR-список</dt>
          <dd className="mt-0.5">
            {node.file ? (
              <>
                <div>{providerName}</div>
                <div className="text-[11px] text-muted-foreground">{node.file}</div>
              </>
            ) : (
              <span className="text-muted-foreground">не сопоставлен</span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Alive</dt>
          <dd className="mt-0.5">
            {node.alive ? (
              <Badge variant="outline" className="text-[10px]">
                {ALIVE_LABELS[node.alive] ?? node.alive}
              </Badge>
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">tcp 16-20</dt>
          <dd className="mt-0.5">
            <Badge variant={severity.badge}>{severity.label}</Badge>
            {node.dpi_method != null && (
              <div className="mt-1 text-[11px] text-muted-foreground">method {node.dpi_method}</div>
            )}
            <div className="mt-1 text-[11px] text-muted-foreground">{node.status_text}</div>
          </dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-muted-foreground">Маршрут</dt>
          <dd className="mt-0.5">
            <Badge
              variant={
                provider?.enabled ? 'default' : provider?.has_source ? 'secondary' : provider ? 'outline' : 'outline'
              }
            >
              {routeLabel}
            </Badge>
            {provider?.has_source && provider.cidr_count > 0 && (
              <div className="mt-1 text-[11px] text-muted-foreground tabular-nums">
                {formatCompactCount(provider.cidr_count)} CIDR
              </div>
            )}
          </dd>
        </div>
      </dl>
    </Card>
  )
}

export default function AnalysisTab({ providers, onNavigateTab }: AnalysisTabProps) {
  const [logText, setLogText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<DpiAnalysisResult | null>(null)

  const providerByFile = useMemo(
    () => new Map(providers.map((item) => [item.filename, item])),
    [providers],
  )

  const recommendationsByLevel = useMemo(() => {
    if (!result?.success) return []
    const order: DpiAnalysisRecommendation['level'][] = ['must', 'should', 'consider', 'skip']
    return order
      .map((level) => ({
        level,
        items: result.recommendations.filter((item) => item.level === level),
      }))
      .filter((group) => group.items.length > 0)
  }, [result])

  const recommendedToEnable = useMemo(() => {
    if (!result?.success) return []
    return (result.actionable_files ?? []).filter((file) => {
      const provider = providerByFile.get(file)
      return provider && provider.has_source && !provider.enabled
    })
  }, [result, providerByFile])

  async function handleAnalyze() {
    const text = logText.trim()
    if (!text) {
      setError('Вставьте лог с результатами проверки tcp 16-20')
      setResult(null)
      return
    }

    setLoading(true)
    setError(null)
    try {
      const response = await analyzeDpiLog(text)
      setResult(response)
      if (!response.success) {
        setError(response.message || 'Не удалось разобрать лог')
      }
    } catch (err) {
      setResult(null)
      setError(err instanceof Error ? err.message : 'Ошибка анализа лога')
    } finally {
      setLoading(false)
    }
  }

  function providerLabel(file: string, fallback?: string) {
    return providerByFile.get(file)?.name ?? fallback ?? file
  }

  function providerStatusHint(file: string) {
    const provider = providerByFile.get(file)
    if (!provider) return 'нет в каталоге'
    if (!provider.has_source) return 'нет на узле — deploy'
    if (provider.enabled) return 'уже включён'
    return 'выключен'
  }

  return (
    <div className="space-y-6">
      <StatusPanel title="Анализ лога DPI checker" icon={FlaskConical}>
        <div className="space-y-2 text-sm text-muted-foreground">
          <p>
            Вставьте лог с{' '}
            <a
              href={DPI_CHECKER_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
            >
              TCP 16-20 checker
              <ExternalLink size={12} />
            </a>
            . Рекомендации рассчитаны для <strong className="font-medium text-foreground">выборочной</strong>{' '}
            маршрутизации CIDR — checker нужно запускать <strong className="font-medium text-foreground">без VPN</strong>.
          </p>
          <p>
            «Detected» означает таймаут POST ~64 KB, а не «сайт не открывается». Для каждого списка показываем узел checker
            и hostname.
          </p>
        </div>
      </StatusPanel>

      <div className="rounded-xl border bg-card p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-sm font-medium">Лог проверки</div>
            <div className="text-xs text-muted-foreground">
              Консоль checker, таблица 6 колонок или 4 колонки (ID · провайдер · alive · DPI)
            </div>
          </div>
          <Button variant="outline" size="sm" asChild>
            <a href={DPI_CHECKER_URL} target="_blank" rel="noopener noreferrer">
              Открыть checker
              <ExternalLink size={14} className="ml-1.5" />
            </a>
          </Button>
        </div>

        <Textarea
          value={logText}
          onChange={(event) => setLogText(event.target.value)}
          placeholder={`Пример:\n[23:08:22.361] DPI checking(#SE.AKM-01)/INFO: alived: yes 🟢\n[23:08:37.363] DPI checking(#SE.AKM-01)/INFO: tcp 16-20: detected❗️, method: 1`}
          className="min-h-[180px] font-mono text-xs"
          spellCheck={false}
        />

        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => void handleAnalyze()} disabled={loading}>
            {loading ? <Loader2 size={16} className="animate-spin" /> : <FlaskConical size={16} />}
            <span className="ml-1.5">Анализировать</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setLogText('')
              setResult(null)
              setError(null)
            }}
            disabled={loading}
          >
            Очистить
          </Button>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>

      {result?.success && (
        <>
          {result.caveats?.length > 0 && (
            <div className="space-y-2">
              {result.caveats.map((caveat) => (
                <div
                  key={caveat.type}
                  className={cn(
                    'rounded-xl border p-4',
                    caveat.severity === 'warning'
                      ? 'border-amber-500/40 bg-amber-500/5'
                      : 'border-sky-500/30 bg-sky-500/5',
                  )}
                >
                  <div className="flex items-start gap-2">
                    {caveat.severity === 'warning' ? (
                      <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-600" />
                    ) : (
                      <Info size={16} className="mt-0.5 shrink-0 text-sky-600" />
                    )}
                    <div>
                      <div className="text-sm font-medium">{caveat.title}</div>
                      <p className="mt-1 text-xs text-muted-foreground">{caveat.message}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              label="Узлов в логе"
              value={result.summary.total_nodes ?? 0}
              icon={FlaskConical}
              accent="cyan"
              sub={`сопоставлено ${result.summary.matched_nodes ?? 0}`}
            />
            <MetricCard
              label="Надёжных рекомендаций"
              value={result.summary.actionable_files ?? 0}
              icon={ShieldAlert}
              accent="red"
              sub="high/medium, must или should"
            />
            <MetricCard
              label="Слабых сигналов"
              value={result.summary.weak_signals ?? 0}
              icon={AlertTriangle}
              accent="amber"
              sub="weak / inconclusive"
            />
            <MetricCard
              label="Можно не включать"
              value={result.recommendations.filter((item) => item.level === 'skip').length}
              icon={CheckCircle2}
              accent="green"
              sub="not detected на узлах"
            />
          </div>

          {recommendedToEnable.length > 0 && onNavigateTab && (
            <div className="rounded-xl border border-primary/30 bg-primary/5 p-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium">Готово к включению на узле</div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {recommendedToEnable.length}{' '}
                  {recommendedToEnable.length === 1 ? 'список' : 'списка'} с надёжной рекомендацией доступны на узле, но
                  выключены.
                </p>
              </div>
              <Button size="sm" onClick={() => onNavigateTab('providers')}>
                Перейти к провайдерам
              </Button>
            </div>
          )}

          <div className="space-y-3">
            <h3 className="text-sm font-medium">Рекомендации по CIDR-спискам</h3>
            <div className="grid gap-3 lg:grid-cols-2">
              {recommendationsByLevel.map(({ level, items }) => {
                const meta = LEVEL_META[level]
                return (
                  <section key={level} className={cn('rounded-xl border p-4', meta.tone)}>
                    <div className="flex items-start gap-2">
                      <meta.icon size={16} className="mt-0.5 shrink-0" />
                      <div className="min-w-0 flex-1 space-y-3">
                        <div className="text-sm font-medium">{meta.title}</div>
                        {items.map((item) => {
                          const provider = providerByFile.get(item.file)
                          const confidence = CONFIDENCE_META[item.confidence]
                          return (
                            <article
                              key={item.file}
                              className="rounded-md border bg-background/70 p-3 space-y-2"
                            >
                              <div className="flex flex-wrap items-start justify-between gap-2">
                                <div className="min-w-0">
                                  <div className="font-medium">{providerLabel(item.file, item.name)}</div>
                                  <div className="text-[11px] text-muted-foreground">{item.file}</div>
                                </div>
                                <div className="flex flex-wrap items-center gap-1.5">
                                  <Badge variant={confidence.variant} className="text-[10px]">
                                    {confidence.label}
                                  </Badge>
                                  {provider?.category && (
                                    <Badge variant="outline" className="text-[10px]">
                                      {providerCategoryLabel(provider.category)}
                                    </Badge>
                                  )}
                                  <Badge
                                    variant={
                                      provider?.enabled
                                        ? 'default'
                                        : provider?.has_source
                                          ? 'secondary'
                                          : 'outline'
                                    }
                                    className="text-[10px]"
                                  >
                                    {providerStatusHint(item.file)}
                                  </Badge>
                                </div>
                              </div>

                              <p className="text-xs text-muted-foreground">{item.reason}</p>

                              {item.trigger_nodes.length > 0 && (
                                <div className="space-y-1.5">
                                  <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                                    {item.level === 'skip' ? 'Узлы checker' : 'Из-за этих узлов'}
                                  </div>
                                  <div className="space-y-1.5">
                                    {item.trigger_nodes.map((node) => (
                                      <NodeChip key={node.node_id} node={node} />
                                    ))}
                                  </div>
                                </div>
                              )}

                              {item.all_nodes.length > 1 && item.level !== 'skip' && (
                                <details className="text-xs">
                                  <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                                    Все узлы провайдера в логе ({item.all_nodes.length})
                                  </summary>
                                  <div className="mt-2 space-y-1.5">
                                    {item.all_nodes.map((node) => (
                                      <NodeChip key={`${item.file}-${node.node_id}`} node={node} />
                                    ))}
                                  </div>
                                </details>
                              )}
                            </article>
                          )
                        })}
                      </div>
                    </div>
                  </section>
                )
              })}
            </div>
          </div>

          {result.unknown_nodes.length > 0 && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
              <div className="text-sm font-medium">Не удалось сопоставить узлы</div>
              <p className="mt-1 text-xs text-muted-foreground">
                {result.unknown_nodes.join(', ')} — для них нет CIDR-списка в каталоге (Contabo, Vultr, Gcore и т.д.).
              </p>
            </div>
          )}

          <div className="rounded-xl border bg-card overflow-hidden">
            <div className="border-b px-4 py-3">
              <div className="text-sm font-medium">Все узлы из лога</div>
              <p className="text-xs text-muted-foreground">
                Полная расшифровка: ID checker → hostname → результат tcp 16-20
              </p>
            </div>
            <div className="p-4">
              <ResponsiveDataView
                mobile={result.nodes.map((node) => {
                  const provider = node.file ? providerByFile.get(node.file) : undefined
                  const routeLabel = provider?.enabled
                    ? 'включён'
                    : provider?.has_source
                      ? 'выключен'
                      : provider
                        ? 'нет на узле'
                        : '—'
                  return (
                    <DpiLogNodeCard
                      key={node.node_id}
                      node={node}
                      provider={provider}
                      providerName={node.file ? providerLabel(node.file) : '—'}
                      routeLabel={routeLabel}
                    />
                  )
                })}
                desktop={
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b bg-muted/30 text-left text-xs text-muted-foreground">
                          <th className="px-4 py-2 font-medium">Узел</th>
                          <th className="px-4 py-2 font-medium">Хост checker</th>
                          <th className="px-4 py-2 font-medium">CIDR-список</th>
                          <th className="px-4 py-2 font-medium">Alive</th>
                          <th className="px-4 py-2 font-medium">tcp 16-20</th>
                          <th className="px-4 py-2 font-medium">Маршрут</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.nodes.map((node) => {
                          const provider = node.file ? providerByFile.get(node.file) : undefined
                          const severity = SEVERITY_META[node.severity] ?? SEVERITY_META.unknown
                          const url = hostUrl(node.host)
                          return (
                            <tr key={node.node_id} className="border-b last:border-0 align-top">
                              <td className="px-4 py-2.5 font-mono text-xs">{node.node_id}</td>
                              <td className="px-4 py-2.5">
                                {node.host ? (
                                  <div>
                                    <a
                                      href={url ?? '#'}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="font-mono text-xs text-primary hover:underline"
                                    >
                                      {node.host}
                                    </a>
                                    {node.checker_country && (
                                      <div className="text-[11px] text-muted-foreground">{node.checker_country}</div>
                                    )}
                                  </div>
                                ) : (
                                  <span className="text-muted-foreground">—</span>
                                )}
                              </td>
                              <td className="px-4 py-2.5">
                                {node.file ? (
                                  <>
                                    <div>{providerLabel(node.file)}</div>
                                    <div className="text-[11px] text-muted-foreground">{node.file}</div>
                                  </>
                                ) : (
                                  <span className="text-muted-foreground">не сопоставлен</span>
                                )}
                              </td>
                              <td className="px-4 py-2.5">
                                {node.alive ? (
                                  <Badge variant="outline" className="text-[10px]">
                                    {ALIVE_LABELS[node.alive] ?? node.alive}
                                  </Badge>
                                ) : (
                                  <span className="text-muted-foreground">—</span>
                                )}
                              </td>
                              <td className="px-4 py-2.5">
                                <Badge variant={severity.badge}>{severity.label}</Badge>
                                {node.dpi_method != null && (
                                  <div className="mt-1 text-[11px] text-muted-foreground">method {node.dpi_method}</div>
                                )}
                                <div className="mt-1 text-[11px] text-muted-foreground">{node.status_text}</div>
                              </td>
                              <td className="px-4 py-2.5">
                                {provider?.enabled ? (
                                  <Badge variant="default">включён</Badge>
                                ) : provider?.has_source ? (
                                  <Badge variant="secondary">выключен</Badge>
                                ) : provider ? (
                                  <Badge variant="outline">нет на узле</Badge>
                                ) : (
                                  <span className="text-muted-foreground">—</span>
                                )}
                                {provider?.has_source && provider.cidr_count > 0 && (
                                  <div className="mt-1 text-[11px] text-muted-foreground tabular-nums">
                                    {formatCompactCount(provider.cidr_count)} CIDR
                                  </div>
                                )}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                }
                mobileClassName="space-y-3"
              />
            </div>
          </div>
        </>
      )}
    </div>
  )
}
