import { useCallback, useEffect, useRef, useState } from 'react'
import { CloudDownload, GitBranch, Play, RefreshCw, Route, Shield } from 'lucide-react'
import {
  ApiError,
  applyRouting,
  applyRoutingPreset,
  generateCidrFromDb,
  getAntifilterStatus,
  getCidrDbStatus,
  getCidrPipelineTask,
  getGameFilters,
  getRoutingOverview,
  refreshAntifilter,
  refreshCidrDb,
  syncGameFilters,
  syncRoutingProviders,
  toggleRoutingProvider,
} from '@/api/client'
import AutoRefreshControl from '@/components/noc/AutoRefreshControl'
import MetricCard from '@/components/noc/MetricCard'
import { NodeBadge } from '@/components/NodeSelector'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import Spinner from '@/components/ui/Spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { useAuth } from '@/context/AuthContext'
import type { AntifilterStatus, CidrDbStatus, CidrPipelineTask, GameFilterItem, RoutingOverview } from '@/types'

const REFRESH_INTERVAL = 60

function formatDt(value?: string | null) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString('ru-RU')
  } catch {
    return value
  }
}

function statusBadgeVariant(status?: string) {
  if (status === 'ok') return 'default' as const
  if (status === 'partial') return 'secondary' as const
  if (status === 'error') return 'destructive' as const
  if (status === 'running') return 'secondary' as const
  return 'outline' as const
}

export default function RoutingPage() {
  const { activeNode } = useNode()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const { success, error: notifyError } = useNotifications()
  const { startGlobal, doneGlobal } = useProgress()
  const [data, setData] = useState<RoutingOverview | null>(null)
  const [cidrDb, setCidrDb] = useState<CidrDbStatus | null>(null)
  const [antifilter, setAntifilter] = useState<AntifilterStatus | null>(null)
  const [pipelineTask, setPipelineTask] = useState<CidrPipelineTask | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [countdown, setCountdown] = useState(REFRESH_INTERVAL)
  const [games, setGames] = useState<GameFilterItem[]>([])
  const [gameModes, setGameModes] = useState<Record<string, string>>({})
  const [filterAntifilter, setFilterAntifilter] = useState(false)

  const loadPipelineMeta = useCallback(async () => {
    try {
      const [dbStatus, afStatus] = await Promise.all([getCidrDbStatus(), getAntifilterStatus()])
      setCidrDb(dbStatus)
      setAntifilter(afStatus)
    } catch {
      /* optional panel */
    }
  }, [])

  const load = useCallback(async (initial = false) => {
    if (initial) {
      setLoading(true)
      startGlobal()
    }
    try {
      setData(await getRoutingOverview())
      await loadPipelineMeta()
      setCountdown(REFRESH_INTERVAL)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки маршрутизации')
    } finally {
      setLoading(false)
      if (initial) doneGlobal()
    }
  }, [startGlobal, doneGlobal, notifyError, loadPipelineMeta])

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const pollTask = useCallback(
    (taskId: string, okMsg: string) => {
      stopPolling()
      pollRef.current = setInterval(async () => {
        try {
          const { task } = await getCidrPipelineTask(taskId)
          setPipelineTask(task)
          if (task.status === 'completed') {
            stopPolling()
            success(okMsg)
            await load()
          } else if (task.status === 'failed') {
            stopPolling()
            notifyError(task.error || task.message || 'Ошибка pipeline')
            await loadPipelineMeta()
          }
        } catch (err) {
          stopPolling()
          notifyError(err instanceof ApiError ? err.message : 'Ошибка отслеживания задачи')
        }
      }, 1500)
    },
    [load, loadPipelineMeta, notifyError, stopPolling, success],
  )

  useEffect(() => () => stopPolling(), [stopPolling])

  useEffect(() => {
    load(true)
    getGameFilters()
      .then((r) => {
        setGames(r.games)
        const modes: Record<string, string> = {}
        r.games.forEach((g) => { modes[g.key] = g.mode })
        setGameModes(modes)
      })
      .catch(() => {})
  }, [load, activeNode?.id])

  useEffect(() => {
    if (!autoRefresh) return
    const tick = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          load()
          return REFRESH_INTERVAL
        }
        return c - 1
      })
    }, 1000)
    return () => clearInterval(tick)
  }, [autoRefresh, load])

  const withPipelineAction = async (fn: () => Promise<{ task_id: string; message: string }>, okMsg: string) => {
    setActionLoading(true)
    try {
      const resp = await fn()
      setPipelineTask({
        task_id: resp.task_id,
        task_type: '',
        status: 'queued',
        message: resp.message,
        progress_percent: 0,
        progress_stage: resp.message,
      })
      pollTask(resp.task_id, okMsg)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка операции')
    } finally {
      setActionLoading(false)
    }
  }

  const withAction = async (fn: () => Promise<unknown>, okMsg: string) => {
    setActionLoading(true)
    try {
      await fn()
      success(okMsg)
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка операции')
    } finally {
      setActionLoading(false)
    }
  }

  if (loading && !data) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner />
      </div>
    )
  }

  const enabledCount = data?.providers.filter((p) => p.enabled).length ?? 0

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Маршрутизация / CIDR</h2>
          <p className="text-sm text-muted-foreground">Управление CIDR-списками провайдеров и маршрутами AntiZapret</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <NodeBadge />
          <AutoRefreshControl
            enabled={autoRefresh}
            countdown={countdown}
            interval={REFRESH_INTERVAL}
            onToggle={() => setAutoRefresh((v) => !v)}
            onRefresh={() => load()}
          />
          {isAdmin && (
            <>
              <Button
                variant="outline"
                size="sm"
                disabled={actionLoading}
                onClick={() => withAction(syncRoutingProviders, 'Синхронизация выполнена')}
              >
                <RefreshCw size={14} className="mr-1" />
                Синхронизировать
              </Button>
              <Button
                size="sm"
                disabled={actionLoading}
                onClick={() => withAction(applyRouting, 'doall.sh выполнен')}
              >
                <Play size={14} className="mr-1" />
                Применить (doall.sh)
              </Button>
            </>
          )}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard title="Провайдеры активны" value={enabledCount} icon={Route} subtitle={`из ${data?.providers.length ?? 0}`} />
        <MetricCard
          title="Маршруты в config"
          value={data?.route_stats.config_include_total ?? 0}
          icon={GitBranch}
          subtitle="*include-ips.txt"
        />
        <MetricCard
          title="route-ips.txt"
          value={data?.route_stats.result_route_ips_count ?? 0}
          icon={Route}
          subtitle={data?.route_stats.result_route_ips_exists ? 'Сгенерирован' : 'Не сгенерирован'}
        />
        <MetricCard title="Пресеты" value={data?.presets.length ?? 0} icon={GitBranch} subtitle="Встроенные" />
      </div>

      {isAdmin && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CloudDownload size={18} />
              CIDR DB Pipeline
            </CardTitle>
            <CardDescription>
              Загрузка провайдеров из интернета в SQLite на контроллере, генерация списков и фильтр antifilter.download
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 text-sm">
              <div>
                <div className="text-muted-foreground">Последнее обновление БД</div>
                <div className="font-medium">{formatDt(cidrDb?.last_refresh_finished)}</div>
                <Badge variant={statusBadgeVariant(cidrDb?.last_refresh_status ?? undefined)} className="mt-1">
                  {cidrDb?.last_refresh_status ?? 'never'}
                </Badge>
              </div>
              <div>
                <div className="text-muted-foreground">CIDR в БД</div>
                <div className="font-mono text-lg">{cidrDb?.total_cidrs ?? 0}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Antifilter</div>
                <div className="font-mono">{antifilter?.cidr_count ?? 0} подсетей</div>
                <div className="text-xs text-muted-foreground">{formatDt(antifilter?.last_refreshed_at)}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Источник</div>
                <div className="text-xs">{cidrDb?.last_refresh_triggered_by ?? '—'}</div>
              </div>
            </div>

            {pipelineTask && ['queued', 'running'].includes(pipelineTask.status) && (
              <div className="rounded-md border bg-muted/40 p-4 space-y-2">
                <div className="flex justify-between text-sm">
                  <span>{pipelineTask.progress_stage || pipelineTask.message}</span>
                  <span>{pipelineTask.progress_percent}%</span>
                </div>
                <Progress value={pipelineTask.progress_percent} />
              </div>
            )}

            <div className="flex flex-wrap gap-2 items-center">
              <Button
                size="sm"
                disabled={actionLoading || (!!pipelineTask && ['queued', 'running'].includes(pipelineTask.status))}
                onClick={() =>
                  withPipelineAction(refreshCidrDb, 'CIDR БД обновлена из интернета')
                }
              >
                <CloudDownload size={14} className="mr-1" />
                Обновить из интернета
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={actionLoading || (!!pipelineTask && ['queued', 'running'].includes(pipelineTask.status))}
                onClick={() => withPipelineAction(refreshAntifilter, 'Antifilter синхронизирован')}
              >
                <Shield size={14} className="mr-1" />
                Antifilter sync
              </Button>
              <label className="flex items-center gap-2 text-sm ml-2">
                <input
                  type="checkbox"
                  checked={filterAntifilter}
                  onChange={(e) => setFilterAntifilter(e.target.checked)}
                />
                Фильтр по antifilter
              </label>
              <Button
                size="sm"
                variant="secondary"
                disabled={actionLoading || (!!pipelineTask && ['queued', 'running'].includes(pipelineTask.status))}
                onClick={() =>
                  withPipelineAction(
                    () => generateCidrFromDb({ filter_by_antifilter: filterAntifilter, apply_after: false }),
                    'CIDR-файлы сгенерированы из БД',
                  )
                }
              >
                Сгенерировать из БД
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={actionLoading || (!!pipelineTask && ['queued', 'running'].includes(pipelineTask.status))}
                onClick={() =>
                  withPipelineAction(
                    () => generateCidrFromDb({ filter_by_antifilter: filterAntifilter, apply_after: true }),
                    'Сгенерировано и применено (doall.sh)',
                  )
                }
              >
                Сгенерировать + doall
              </Button>
            </div>

            {(cidrDb?.alerts?.length ?? 0) > 0 && (
              <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-200">
                {cidrDb?.alerts?.map((a) => (
                  <div key={a}>{a}</div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <Tabs defaultValue="providers">
        <TabsList>
          <TabsTrigger value="providers">Провайдеры</TabsTrigger>
          <TabsTrigger value="presets">Пресеты</TabsTrigger>
          <TabsTrigger value="games">Игры</TabsTrigger>
        </TabsList>

        <TabsContent value="providers">
          <Card>
            <CardHeader>
              <CardTitle>CIDR-провайдеры</CardTitle>
              <CardDescription>Включение/отключение списков → AP-*-include-ips.txt в config AntiZapret</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Провайдер</TableHead>
                    <TableHead>Категория</TableHead>
                    <TableHead className="text-right">CIDR (файл)</TableHead>
                    <TableHead className="text-right">CIDR (БД)</TableHead>
                    <TableHead>БД refresh</TableHead>
                    <TableHead>Статус</TableHead>
                    {isAdmin && <TableHead className="text-right">Действие</TableHead>}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data?.providers.map((p) => {
                    const dbMeta = cidrDb?.providers?.[p.filename]
                    return (
                    <TableRow key={p.filename}>
                      <TableCell>
                        <div className="font-medium">{p.name}</div>
                        <div className="text-xs text-muted-foreground">{p.filename}</div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{p.category}</Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono">{p.cidr_count}</TableCell>
                      <TableCell className="text-right font-mono">{dbMeta?.cidr_count ?? '—'}</TableCell>
                      <TableCell className="text-xs">
                        <Badge variant={statusBadgeVariant(dbMeta?.refresh_status)}>{dbMeta?.refresh_status ?? 'never'}</Badge>
                        <div className="text-muted-foreground mt-1">{formatDt(dbMeta?.last_refreshed_at)}</div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={p.enabled ? 'default' : 'secondary'}>
                          {p.enabled ? 'Включён' : 'Выключен'}
                        </Badge>
                        {!p.has_source && <span className="ml-2 text-xs text-amber-600">нет источника</span>}
                      </TableCell>
                      {isAdmin && (
                        <TableCell className="text-right">
                          <Button
                            size="sm"
                            variant={p.enabled ? 'outline' : 'default'}
                            disabled={actionLoading || (!p.has_source && !p.enabled)}
                            onClick={() =>
                              withAction(
                                () => toggleRoutingProvider(p.filename, !p.enabled),
                                p.enabled ? `${p.name} отключён` : `${p.name} включён`,
                              )
                            }
                          >
                            {p.enabled ? 'Отключить' : 'Включить'}
                          </Button>
                        </TableCell>
                      )}
                    </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="presets">
          <div className="grid gap-4 md:grid-cols-2">
            {data?.presets.map((preset) => (
              <Card key={preset.key}>
                <CardHeader>
                  <CardTitle className="text-base">{preset.name}</CardTitle>
                  <CardDescription>{preset.description}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex flex-wrap gap-1">
                    {preset.providers.map((f) => (
                      <Badge key={f} variant="outline" className="text-xs">
                        {data.providers.find((p) => p.filename === f)?.name ?? f}
                      </Badge>
                    ))}
                  </div>
                  {isAdmin && (
                    <Button
                      size="sm"
                      disabled={actionLoading}
                      onClick={() =>
                        withAction(() => applyRoutingPreset(preset.key), `Пресет «${preset.name}» применён`)
                      }
                    >
                      Применить пресет
                    </Button>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="games">
          <Card>
            <CardHeader>
              <CardTitle>Игровые фильтры</CardTitle>
              <CardDescription>Домены и IP игр → AZ-Game-include-* в config AntiZapret</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {games.map((g) => (
                  <div key={g.key} className="flex items-center justify-between rounded-md border p-3">
                    <div>
                      <div className="font-medium text-sm">{g.title}</div>
                      <div className="text-xs text-muted-foreground">{g.subtitle}</div>
                    </div>
                    {isAdmin ? (
                      <select
                        className="rounded border bg-background px-2 py-1 text-xs"
                        value={gameModes[g.key] || 'none'}
                        onChange={(e) => setGameModes({ ...gameModes, [g.key]: e.target.value })}
                      >
                        <option value="none">—</option>
                        <option value="include">Включить</option>
                        <option value="exclude">Исключить</option>
                      </select>
                    ) : (
                      <Badge variant="outline">{gameModes[g.key] || 'none'}</Badge>
                    )}
                  </div>
                ))}
              </div>
              {isAdmin && (
                <Button
                  disabled={actionLoading}
                  onClick={() => withAction(() => syncGameFilters(gameModes), 'Игровые фильтры синхронизированы')}
                >
                  Синхронизировать и применить
                </Button>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {isAdmin && (
        <Card>
          <CardHeader>
            <CardTitle>Файлы маршрутизации</CardTitle>
            <CardDescription>include-ips, exclude-ips, forward-ips, drop-ips — в Редакторе файлов</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Ручное редактирование базовых файлов доступно на вкладке «Настройки». После изменений нажмите «Применить (doall.sh)».
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
