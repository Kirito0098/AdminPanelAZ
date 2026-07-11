import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import * as api from '@/api/client'
import { useAuth } from '@/context/AuthContext'
import type { Node, NodeHaContext, NodeSyncGroup } from '@/types'

interface NodeContextValue {
  activeNode: Node | null
  activeNodeHa: NodeHaContext | null
  nodes: Node[]
  syncGroups: NodeSyncGroup[]
  syncGroupsLoaded: boolean
  loading: boolean
  refresh: () => Promise<void>
  refreshNodes: () => Promise<void>
  refreshSyncGroups: () => Promise<void>
  activate: (id: number) => Promise<void>
}

const NodeContext = createContext<NodeContextValue | null>(null)

export function NodeProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const [activeNode, setActiveNode] = useState<Node | null>(null)
  const [activeNodeHa, setActiveNodeHa] = useState<NodeHaContext | null>(null)
  const [nodes, setNodes] = useState<Node[]>([])
  const [syncGroups, setSyncGroups] = useState<NodeSyncGroup[]>([])
  const [syncGroupsLoaded, setSyncGroupsLoaded] = useState(false)
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

  const refreshSyncGroups = useCallback(async () => {
    if (!user || user.role !== 'admin') {
      setSyncGroups([])
      setSyncGroupsLoaded(false)
      return
    }
    try {
      setSyncGroups(await api.getNodeSyncGroups())
    } catch {
      setSyncGroups([])
    } finally {
      setSyncGroupsLoaded(true)
    }
  }, [user])

  const activate = useCallback(
    async (id: number) => {
      const data = await api.activateNode(id)
      setActiveNode(data.node)
      setActiveNodeHa(data.ha ?? null)
      await Promise.all([refreshNodes(), refreshSyncGroups()])
    },
    [refreshNodes, refreshSyncGroups],
  )

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    refreshNodes()
  }, [refreshNodes])

  useEffect(() => {
    refreshSyncGroups()
  }, [refreshSyncGroups])

  useEffect(() => {
    if (!user) return

    const interval = window.setInterval(() => {
      void refresh()
      if (user.role === 'admin') {
        void refreshNodes()
        void refreshSyncGroups()
      }
    }, 45_000)

    const onVisible = () => {
      if (document.visibilityState === 'visible') void refresh()
    }
    document.addEventListener('visibilitychange', onVisible)

    return () => {
      window.clearInterval(interval)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [user, refresh, refreshNodes, refreshSyncGroups])

  const value = useMemo(
    () => ({
      activeNode,
      activeNodeHa,
      nodes,
      syncGroups,
      syncGroupsLoaded,
      loading,
      refresh,
      refreshNodes,
      refreshSyncGroups,
      activate,
    }),
    [
      activeNode,
      activeNodeHa,
      nodes,
      syncGroups,
      syncGroupsLoaded,
      loading,
      refresh,
      refreshNodes,
      refreshSyncGroups,
      activate,
    ],
  )

  return <NodeContext.Provider value={value}>{children}</NodeContext.Provider>
}

export function useNode() {
  const ctx = useContext(NodeContext)
  if (!ctx) throw new Error('useNode must be used within NodeProvider')
  return ctx
}
