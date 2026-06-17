import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import * as api from '@/api/client'
import { useAuth } from '@/context/AuthContext'
import type { Node, NodeHaContext } from '@/types'

interface NodeContextValue {
  activeNode: Node | null
  activeNodeHa: NodeHaContext | null
  nodes: Node[]
  loading: boolean
  refresh: () => Promise<void>
  refreshNodes: () => Promise<void>
  activate: (id: number) => Promise<void>
}

const NodeContext = createContext<NodeContextValue | null>(null)

export function NodeProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const [activeNode, setActiveNode] = useState<Node | null>(null)
  const [activeNodeHa, setActiveNodeHa] = useState<NodeHaContext | null>(null)
  const [nodes, setNodes] = useState<Node[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    if (!user) {
      setActiveNode(null)
      setActiveNodeHa(null)
      setLoading(false)
      return
    }
    try {
      const data = await api.getActiveNode()
      setActiveNode(data.node)
      setActiveNodeHa(data.ha ?? null)
    } catch {
      setActiveNode(null)
      setActiveNodeHa(null)
    } finally {
      setLoading(false)
    }
  }, [user])

  const refreshNodes = useCallback(async () => {
    if (!user || user.role !== 'admin') {
      setNodes([])
      return
    }
    try {
      setNodes(await api.getNodes())
    } catch {
      setNodes([])
    }
  }, [user])

  const activate = useCallback(async (id: number) => {
    const data = await api.activateNode(id)
    setActiveNode(data.node)
    setActiveNodeHa(data.ha ?? null)
    await refreshNodes()
  }, [refreshNodes])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    refreshNodes()
  }, [refreshNodes])

  useEffect(() => {
    if (!user) return

    const interval = window.setInterval(() => {
      void refresh()
      if (user.role === 'admin') void refreshNodes()
    }, 45_000)

    const onVisible = () => {
      if (document.visibilityState === 'visible') void refresh()
    }
    document.addEventListener('visibilitychange', onVisible)

    return () => {
      window.clearInterval(interval)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [user, refresh, refreshNodes])

  const value = useMemo(
    () => ({ activeNode, activeNodeHa, nodes, loading, refresh, refreshNodes, activate }),
    [activeNode, activeNodeHa, nodes, loading, refresh, refreshNodes, activate],
  )

  return <NodeContext.Provider value={value}>{children}</NodeContext.Provider>
}

export function useNode() {
  const ctx = useContext(NodeContext)
  if (!ctx) throw new Error('useNode must be used within NodeProvider')
  return ctx
}
