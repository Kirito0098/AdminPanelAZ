import { useIntervalWhenVisible } from '@/hooks/useIntervalWhenVisible'
import { getAccessToken } from '@/lib/accessToken'
import { getWebSessionId } from '@/lib/webSession'

import { apiBase as API_BASE } from '@/lib/panelBase'
const HEARTBEAT_INTERVAL_MS = 60_000

async function sendHeartbeat(onRevoked?: () => void) {
  const token = getAccessToken()
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

export function useSessionHeartbeat(enabled: boolean, onRevoked?: () => void) {
  useIntervalWhenVisible(
    () => {
      void sendHeartbeat(onRevoked)
    },
    HEARTBEAT_INTERVAL_MS,
    {
      enabled,
      runOnMount: true,
      onBecomeVisible: () => {
        void sendHeartbeat(onRevoked)
      },
    },
  )
}
