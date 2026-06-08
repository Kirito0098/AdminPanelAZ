import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import * as api from '@/api/client'
import { useAuth } from '@/context/AuthContext'
import type { Node } from '@/types'

interface NodeContextValue {
  activeNode: Node | null
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
  const [nodes, setNodes] = useState<Node[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    if (!user) {
      setActiveNode(null)
      setLoading(false)
      return
    }
    try {
      const { node } = await api.getActiveNode()
      setActiveNode(node)
    } catch {
      setActiveNode(null)
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
    const { node } = await api.activateNode(id)
    setActiveNode(node)
    await refreshNodes()
  }, [refreshNodes])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    refreshNodes()
  }, [refreshNodes])

  const value = useMemo(
    () => ({ activeNode, nodes, loading, refresh, refreshNodes, activate }),
    [activeNode, nodes, loading, refresh, refreshNodes, activate],
  )

  return <NodeContext.Provider value={value}>{children}</NodeContext.Provider>
}

export function useNode() {
  const ctx = useContext(NodeContext)
  if (!ctx) throw new Error('useNode must be used within NodeProvider')
  return ctx
}
