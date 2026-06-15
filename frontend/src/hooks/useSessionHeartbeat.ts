import { useEffect } from 'react'
import { getWebSessionId } from '@/lib/webSession'

const API_BASE = import.meta.env.VITE_API_URL || '/api'
const HEARTBEAT_INTERVAL_MS = 60_000

export function useSessionHeartbeat(enabled: boolean, onRevoked?: () => void) {
  useEffect(() => {
    if (!enabled) return

    const sendHeartbeat = async () => {
      if (document.visibilityState !== 'visible') return
      const token = localStorage.getItem('token')
      const sessionId = getWebSessionId()
      if (!token || !sessionId) return

      try {
        const resp = await fetch(`${API_BASE}/session-heartbeat`, {
          method: 'GET',
          cache: 'no-store',
          credentials: 'include',
          headers: {
            Authorization: `Bearer ${token}`,
            'X-Web-Session-Id': sessionId,
          },
        })
        if (resp.ok) {
          const data = (await resp.json()) as { revoked?: boolean }
          if (data.revoked) onRevoked?.()
        }
      } catch {
        /* ignore background heartbeat errors */
      }
    }

    sendHeartbeat()
    const timer = window.setInterval(sendHeartbeat, HEARTBEAT_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [enabled, onRevoked])
}
