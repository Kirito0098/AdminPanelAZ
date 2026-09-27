/**
 * Answers about the active node can arrive after the tab switched to another node or after a newer
 * request of the same kind: only the latest request for the node shown now may apply its answer.
 */
export function createLatestRequest<S>(initialScope: S) {
  let scope = initialScope
  let seq = 0

  return {
    /** The shown node changed: answers to requests started before no longer apply. */
    reset(next: S): void {
      scope = next
      seq += 1
    },
    /** Starts a request for `forScope` (the shown node by default); the check tells whether its answer still applies. */
    begin(forScope: S = scope): () => boolean {
      if (!Object.is(forScope, scope)) return () => false
      seq += 1
      const token = seq
      return () => token === seq
    },
  }
}

export type LatestRequest<S> = ReturnType<typeof createLatestRequest<S>>

export interface LatestRequestHandlers<T> {
  apply: (value: T) => void
  fail: (err: unknown) => void
  /** Clears the loading flag; a newer request set it again and clears it itself. */
  settle?: () => void
}

/** Runs a request for the shown node and handles its answer only while it is the latest one. */
export async function runLatest<S, T>(
  requests: LatestRequest<S>,
  load: () => Promise<T>,
  { apply, fail, settle }: LatestRequestHandlers<T>,
): Promise<void> {
  const isCurrent = requests.begin()
  let value: T
  try {
    value = await load()
  } catch (err) {
    if (isCurrent()) {
      fail(err)
      settle?.()
    }
    return
  }
  if (!isCurrent()) return
  apply(value)
  settle?.()
}
