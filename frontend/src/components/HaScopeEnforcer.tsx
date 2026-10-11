import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { ApiError } from '@/api/client'
import { useAuth } from '@/context/AuthContext'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { isHaGroupScopePath } from '@/lib/haNodeScope'

export default function HaScopeEnforcer() {
  const location = useLocation()
  const { user } = useAuth()
  const { activeNodeHa, loading, activate } = useNode()
  const { info, warning, error } = useNotifications()
  const enforcingRef = useRef(false)
  // NodeContext re-polls the active node every 45 s; without this a failed switch would be retried and reported each time.
  const failedPrimaryRef = useRef<number | null>(null)
  const isAdmin = user?.role === 'admin'

  useEffect(() => {
    // Switching the active node is admin-only on the server; users still get `ha` for a replica.
    if (!isAdmin) return
    if (loading || enforcingRef.current) return
    if (!isHaGroupScopePath(location.pathname)) return
    if (activeNodeHa?.role !== 'replica') return
    const primaryId = activeNodeHa.primary_node_id
    if (failedPrimaryRef.current === primaryId) return

    enforcingRef.current = true
    const primaryName = activeNodeHa.primary_node_name ?? String(primaryId)

    void activate(primaryId)
      .then(() => {
        info(`HA: переключено на primary «${primaryName}»`)
      })
      .catch((err: unknown) => {
        failedPrimaryRef.current = primaryId
        if (err instanceof ApiError && err.status === 403) {
          warning(`HA: нет прав переключиться на primary «${primaryName}», страница показывает данные реплики`)
          return
        }
        const reason = err instanceof ApiError ? err.message : 'ошибка сети'
        error(`HA: не удалось переключиться на primary «${primaryName}»: ${reason}`)
      })
      .finally(() => {
        enforcingRef.current = false
      })
  }, [isAdmin, location.pathname, activeNodeHa, loading, activate, info, warning, error])

  return null
}
