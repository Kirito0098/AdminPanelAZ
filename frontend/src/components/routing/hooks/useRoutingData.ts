import { useCallback, useEffect, useRef, useState } from 'react'
import type { MutableRefObject } from 'react'
import {
  getAntifilterStatus,
  getCidrDbStatus,
  getCidrDbStatusSummary,
  getRoutingOverview,
} from '@/api/client'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { useIntervalWhenVisible } from '@/hooks/useIntervalWhenVisible'
import { createLatestRequest } from '@/lib/latestRequest'
import type { AntifilterStatus, CidrDbStatus, RoutingOverview } from '@/types'
import { errorMessage } from './errors'
import { REFRESH_INTERVAL } from './types'
import type { LoadRouting, PipelineMetaOptions, ReloadPipelineMeta } from './types'

type LoadPipelineMetaOptions = PipelineMetaOptions & { guard?: () => boolean }

interface Args {
  /** Shown node id; answers of requests for another node are dropped. */
  nodeId: number | null
  nodeLoading: boolean
  syncActivePipelineTask: (task: NonNullable<CidrDbStatus['active_task']>) => void
  loadRef: MutableRefObject<LoadRouting>
  loadPipelineMetaRef: MutableRefObject<ReloadPipelineMeta>
}

/** Routing overview and CIDR meta loading: latest-request dedup, auto-refresh deadline. */
export function useRoutingData({
  nodeId,
  nodeLoading,
  syncActivePipelineTask,
  loadRef,
  loadPipelineMetaRef,
}: Args) {
  const { success, error: notifyError } = useNotifications()
  const { startGlobal, doneGlobal } = useProgress()

  const [data, setData] = useState<RoutingOverview | null>(null)
  const [cidrDb, setCidrDb] = useState<CidrDbStatus | null>(null)
  const [antifilter, setAntifilter] = useState<AntifilterStatus | null>(null)

  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(false)
  // Only the deadline lives in the hook: the ticking seconds are rendered by RoutingPageHeader,
  // so a 1 Hz counter no longer re-renders the whole page tree.
  const [nextRefreshAt, setNextRefreshAt] = useState<number | null>(null)

  // Answers only apply to the node they were requested for, and only while no newer request is out.
  const [latestNodeRequest] = useState(() => createLatestRequest<number | null>(null))
  const inFlightRef = useRef<{ scope: number | null; full: boolean; promise: Promise<void> } | null>(null)
  const refreshDueRef = useRef(false)

  const loadPipelineMeta = useCallback(
    async (opts: LoadPipelineMetaOptions = {}) => {
      const guard = opts.guard
      const stale = () => guard !== undefined && !guard()
      try {
        if (opts.light) {
          const summary = await getCidrDbStatusSummary()
          if (stale()) return
          setCidrDb((prev) =>
            prev
              ? {
                  ...prev,
                  total_cidrs: summary.total_cidrs ?? prev.total_cidrs,
                  active_task: summary.active_task ?? prev.active_task,
                }
              : prev,
          )
          if (summary.active_task) {
            syncActivePipelineTask(summary.active_task)
          }
          return
        }
        const [dbStatus, afStatus] = await Promise.all([getCidrDbStatus(), getAntifilterStatus()])
        if (stale()) return
        setCidrDb(dbStatus)
        setAntifilter(afStatus)
        if (dbStatus.active_task) {
          syncActivePipelineTask(dbStatus.active_task)
        }
      } catch {
        /* optional panel */
      }
    },
    [syncActivePipelineTask],
  )

  // Pipeline progress comes from usePipelineTaskPoll (5s). Do not dual-poll
  // /cidr-db/status/summary every 10s while a task is already tracked.

  const startLoad = useCallback(
    (opts: { initial?: boolean; manual?: boolean; fullMeta?: boolean; scope: number | null }): Promise<void> => {
      const { initial = false, manual = false, fullMeta = false, scope } = opts
      const isCurrent = latestNodeRequest.begin(scope)
      // The shown node is gone (or a newer request took over) — do not even fire the request.
      if (!isCurrent()) return Promise.resolve()
      // Auto-refresh: light CIDR meta only (summary). Full ASN/artifacts status
      // on initial load, manual refresh, and after pipeline completion.
      const wantFullMeta = fullMeta || initial || manual

      if (initial) {
        setLoading(true)
        startGlobal()
      } else if (manual) {
        setRefreshing(true)
      }

      let tracked: Promise<void> | null = null
      const run = async () => {
        try {
          const [overview] = await Promise.all([
            getRoutingOverview(),
            loadPipelineMeta({ ...(wantFullMeta ? {} : { light: true }), guard: isCurrent }),
          ])
          if (!isCurrent()) return
          setData(overview)
          if (manual) success('Данные маршрутизации обновлены')
        } catch (err) {
          if (isCurrent()) notifyError(errorMessage(err, 'Ошибка загрузки маршрутизации'))
        } finally {
          if (inFlightRef.current?.promise === tracked) inFlightRef.current = null
          if (isCurrent()) {
            // Re-arm the deadline on failure too: a broken request must not retry every tick.
            setNextRefreshAt(Date.now() + REFRESH_INTERVAL * 1000)
            setLoading(false)
            setRefreshing(false)
            if (initial) doneGlobal()
          }
        }
      }
      tracked = run()
      inFlightRef.current = { scope, full: wantFullMeta, promise: tracked }
      return tracked
    },
    [startGlobal, doneGlobal, loadPipelineMeta, success, latestNodeRequest, notifyError],
  )

  const load = useCallback(
    (opts: { initial?: boolean; manual?: boolean; fullMeta?: boolean } = {}): Promise<void> => {
      const { initial = false, manual = false, fullMeta = false } = opts
      const scope = nodeId
      const wantFullMeta = fullMeta || initial || manual
      const running = inFlightRef.current
      // Auto-refresh and manual refresh must not hit the endpoint twice. A heavier request
      // (manual/full meta) waits for the light one instead of being swallowed by it.
      if (running && running.scope === scope) {
        if (!wantFullMeta || running.full) return running.promise
        return running.promise.then(() => startLoad({ initial, manual, fullMeta, scope }))
      }
      return startLoad({ initial, manual, fullMeta, scope })
    },
    [nodeId, startLoad],
  )

  useEffect(() => {
    loadRef.current = load
    loadPipelineMetaRef.current = loadPipelineMeta
  }, [load, loadPipelineMeta, loadRef, loadPipelineMetaRef])

  useEffect(() => {
    // The shown node changed (or the node list was reloaded): answers of requests started
    // before it no longer describe the page, so drop them and start a request for the new node.
    latestNodeRequest.reset(nodeId)
    inFlightRef.current = null
    if (nodeLoading) return
    void load({ initial: true })
    // Reload only when active node changes, not when load callback identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeLoading, nodeId, latestNodeRequest])

  // Enabling auto-refresh arms the first deadline; later loads re-arm it themselves.
  useEffect(() => {
    if (!autoRefresh) return
    setNextRefreshAt((prev) =>
      prev !== null && prev > Date.now() ? prev : Date.now() + REFRESH_INTERVAL * 1000,
    )
  }, [autoRefresh])

  useIntervalWhenVisible(
    () => {
      if (nextRefreshAt === null || Date.now() < nextRefreshAt) return
      if (refreshDueRef.current) return
      refreshDueRef.current = true
      void load().finally(() => {
        refreshDueRef.current = false
      })
    },
    1000,
    {
      enabled: autoRefresh,
      onBecomeVisible: () => {
        void load()
      },
    },
  )

  return {
    data,
    cidrDb,
    antifilter,
    loading,
    refreshing,
    autoRefresh,
    setAutoRefresh,
    nextRefreshAt,
    load,
  }
}
