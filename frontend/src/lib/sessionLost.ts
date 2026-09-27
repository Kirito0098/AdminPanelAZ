const listeners = new Set<() => void>()

/** Subscribe to the server refusing to renew the session (refresh token expired or revoked). */
export function onSessionLost(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function notifySessionLost(): void {
  for (const listener of [...listeners]) listener()
}
