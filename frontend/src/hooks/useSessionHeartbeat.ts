import { useIntervalWhenVisible } from '@/hooks/useIntervalWhenVisible'
import { getWebSessionId } from '@/lib/webSession'

import { apiBase as API_BASE } from '@/lib/panelBase'
const HEARTBEAT_INTERVAL_MS = 60_000

export function useSessionHeartbeat(enabled: boolean, onRevoked?: () => void) {
  useIntervalWhenVisible(
    () => {
      const token = localStorage.getItem('token')
      const sessionId = getWebSessionId()
      if (!token || !sessionId) return

      void (async () => {
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
      })()
    },
    HEARTBEAT_INTERVAL_MS,
    {
      enabled,
      runOnMount: true,
      onBecomeVisible: () => {
        const token = localStorage.getItem('token')
        const sessionId = getWebSessionId()
        if (!token || !sessionId) return
        void fetch(`${API_BASE}/session-heartbeat`, {
          method: 'GET',
          cache: 'no-store',
          credentials: 'include',
          headers: {
            Authorization: `Bearer ${token}`,
            'X-Web-Session-Id': sessionId,
          },
        })
          .then(async (resp) => {
            if (!resp.ok) return
            const data = (await resp.json()) as { revoked?: boolean }
            if (data.revoked) onRevoked?.()
          })
          .catch(() => {})
      },
    },
  )
}
