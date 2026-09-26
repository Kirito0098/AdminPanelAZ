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
