import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { isHaGroupScopePath } from '@/lib/haNodeScope'

export default function HaScopeEnforcer() {
  const location = useLocation()
  const { activeNodeHa, loading, activate } = useNode()
  const { info } = useNotifications()
  const enforcingRef = useRef(false)

  useEffect(() => {
    if (loading || enforcingRef.current) return
    if (!isHaGroupScopePath(location.pathname)) return
    if (activeNodeHa?.role !== 'replica') return

    enforcingRef.current = true
    const primaryId = activeNodeHa.primary_node_id
    const primaryName = activeNodeHa.primary_node_name ?? String(primaryId)

    void activate(primaryId)
      .then(() => {
        info(`HA: переключено на primary «${primaryName}»`)
      })
      .finally(() => {
        enforcingRef.current = false
      })
  }, [location.pathname, activeNodeHa, loading, activate, info])

  return null
}
