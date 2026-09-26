import { useEffect, useState } from 'react'
import { createLatestRequest } from '@/lib/latestRequest'

/**
 * Requests about the node the tab shows. Call it before the effects that load data: when `scope`
 * (the active node) changes, answers to requests started for the previous node are dropped.
 */
export function useLatestRequest<S>(scope: S) {
  const [requests] = useState(() => createLatestRequest(scope))
  useEffect(() => {
    requests.reset(scope)
  }, [requests, scope])
  return requests
}
