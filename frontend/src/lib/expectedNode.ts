/**
 * The active node is one panel-wide setting: another tab, admin, the Telegram bot or the Mini App
 * can switch it. Write requests name the node this tab shows, and the server refuses them (409)
 * when the active node is a different one.
 */

export const EXPECTED_NODE_HEADER = 'X-Expected-Node-Id'
export const ACTIVE_NODE_CHANGED_CODE = 'active_node_changed'

const READ_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

let expectedNodeId: number | null = null
const listeners = new Set<() => void>()

export function getExpectedNodeId(): number | null {
  return expectedNodeId
}

export function setExpectedNodeId(id: number | null): void {
  expectedNodeId = id
}

export function applyExpectedNodeHeader(headers: Headers, method?: string): void {
  if (expectedNodeId === null) return
  if (READ_METHODS.has((method || 'GET').toUpperCase())) return
  if (!headers.has(EXPECTED_NODE_HEADER)) headers.set(EXPECTED_NODE_HEADER, String(expectedNodeId))
}

export function isActiveNodeChangedPayload(payload: unknown): boolean {
  if (!payload || typeof payload !== 'object' || !('detail' in payload)) return false
  const detail = (payload as { detail: unknown }).detail
  return (
    typeof detail === 'object' &&
    detail !== null &&
    (detail as { code?: unknown }).code === ACTIVE_NODE_CHANGED_CODE
  )
}

export function onActiveNodeChanged(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function notifyActiveNodeChanged(): void {
  for (const listener of [...listeners]) listener()
}

/** A tab never swaps its node silently: unsaved forms would be applied to another server. */
export function decideActiveNodeRefresh(
  shownNodeId: number | null,
  serverNodeId: number | null,
): 'show' | 'changed-elsewhere' {
  if (shownNodeId === null || serverNodeId === null || shownNodeId === serverNodeId) return 'show'
  return 'changed-elsewhere'
}

export type ActiveNodeRefreshOutcome = 'show' | 'changed-elsewhere' | 'stale'

/**
 * Tracks the node a tab shows. A poll answered around an activation from this tab reports the
 * previous node and is dropped, so it is not mistaken for a switch made elsewhere.
 */
export function createActiveNodeTracker() {
  let shownNodeId: number | null = null
  let activationSeq = 0

  const show = (id: number | null) => {
    shownNodeId = id
    setExpectedNodeId(id)
  }

  return {
    show,
    beginRefresh: (): number => activationSeq,
    classifyRefresh: (token: number, serverNodeId: number | null): ActiveNodeRefreshOutcome =>
      token !== activationSeq ? 'stale' : decideActiveNodeRefresh(shownNodeId, serverNodeId),
    beginActivation: (): void => {
      activationSeq += 1
    },
    finishActivation: (id: number | null): void => {
      activationSeq += 1
      show(id)
    },
  }
}
