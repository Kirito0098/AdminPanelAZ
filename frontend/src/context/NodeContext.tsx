import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import * as api from '@/api/client'
import { useAuth } from '@/context/AuthContext'
import { useIntervalWhenVisible } from '@/hooks/useIntervalWhenVisible'
import { createActiveNodeTracker, deleteNodeInTab, onActiveNodeChanged } from '@/lib/expectedNode'
import type { Node, NodeHaContext, NodeSyncGroup } from '@/types'

interface ActiveNodeState {
  node: Node | null
  ha: NodeHaContext | null
}

interface NodeContextValue {
  activeNode: Node | null
  activeNodeHa: NodeHaContext | null
  /** Active node switched elsewhere (other tab, admin, bot) while this tab still shows ``activeNode``. */
  activeNodeChangedElsewhere: Node | null
  adoptActiveNodeChangedElsewhere: () => void
  nodes: Node[]
  syncGroups: NodeSyncGroup[]
  syncGroupsLoaded: boolean
  loading: boolean
  refresh: () => Promise<void>
  refreshNodes: () => Promise<void>
  refreshSyncGroups: () => Promise<void>
  applySyncGroups: (groups: NodeSyncGroup[]) => void
  activate: (id: number) => Promise<void>
  /** Deleting the node this tab shows moves the tab to the node the server made active. */
  deleteNode: (id: number) => Promise<void>
}

const NodeContext = createContext<NodeContextValue | null>(null)

export function NodeProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const [activeNode, setActiveNode] = useState<Node | null>(null)
  const [activeNodeHa, setActiveNodeHa] = useState<NodeHaContext | null>(null)
  const [changedElsewhere, setChangedElsewhere] = useState<ActiveNodeState | null>(null)
  const trackerRef = useRef(createActiveNodeTracker())
  const [nodes, setNodes] = useState<Node[]>([])
  const [syncGroups, setSyncGroups] = useState<NodeSyncGroup[]>([])
  const [syncGroupsLoaded, setSyncGroupsLoaded] = useState(false)
  const [loading, setLoading] = useState(true)

  const showActiveNode = useCallback((state: ActiveNodeState) => {
    trackerRef.current.show(state.node?.id ?? null)
    setActiveNode(state.node)
    setActiveNodeHa(state.ha)
    setChangedElsewhere(null)
  }, [])

  const refresh = useCallback(async () => {
    if (!user) {
      showActiveNode({ node: null, ha: null })
      setLoading(false)
      return
    }
    const tracker = trackerRef.current
    const token = tracker.beginRefresh()
    try {
      const data = await api.getActiveNode()
      const state = { node: data.node, ha: data.ha ?? null }
      const outcome = tracker.classifyRefresh(token, data.node?.id ?? null)
      if (outcome === 'changed-elsewhere') setChangedElsewhere(state)
      else if (outcome === 'show') showActiveNode(state)
    } catch {
      if (tracker.classifyRefresh(token, null) !== 'stale') showActiveNode({ node: null, ha: null })
    } finally {
      setLoading(false)
    }
  }, [user, showActiveNode])

  const refreshNodes = useCallback(async () => {
    if (!user || user.role !== 'admin') {
      setNodes([])
      return
    }
    try {
      setNodes(await api.getNodes())
    } catch (err) {
      setNodes([])
      throw err
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

  const applySyncGroups = useCallback((groups: NodeSyncGroup[]) => {
    setSyncGroups(groups)
    setSyncGroupsLoaded(true)
  }, [])

  const activate = useCallback(
    async (id: number) => {
      trackerRef.current.beginActivation()
      const data = await api.activateNode(id)
      trackerRef.current.finishActivation(data.node?.id ?? null)
      showActiveNode({ node: data.node, ha: data.ha ?? null })
      await Promise.all([
        refreshNodes().catch(() => {}),
        refreshSyncGroups(),
      ])
    },
    [refreshNodes, refreshSyncGroups, showActiveNode],
  )

  const deleteNode = useCallback(
    async (id: number) => {
      const outcome = await deleteNodeInTab(trackerRef.current, id, {
        deleteNode: api.deleteNode,
        getActiveNode: api.getActiveNode,
      })
      setNodes((prev) => prev.filter((node) => node.id !== id))
      if (outcome.moved) {
        showActiveNode({ node: outcome.active?.node ?? null, ha: outcome.active?.ha ?? null })
      } else {
        setChangedElsewhere((prev) => (prev?.node?.id === id ? null : prev))
      }
    },
    [showActiveNode],
  )

  const adoptActiveNodeChangedElsewhere = useCallback(() => {
    if (changedElsewhere) showActiveNode(changedElsewhere)
  }, [changedElsewhere, showActiveNode])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => onActiveNodeChanged(() => void refresh()), [refresh])

  useEffect(() => {
    void refreshNodes().catch(() => {})
  }, [refreshNodes])

  useEffect(() => {
    void refreshSyncGroups()
  }, [refreshSyncGroups])

  useIntervalWhenVisible(
    () => {
      void refresh()
      if (user?.role === 'admin') {
        void refreshNodes().catch(() => {})
        void refreshSyncGroups()
      }
    },
    45_000,
    {
      enabled: Boolean(user),
      onBecomeVisible: () => {
        void refresh()
        if (user?.role === 'admin') {
          void refreshNodes().catch(() => {})
          void refreshSyncGroups()
        }
      },
    },
  )

  const value = useMemo(
    () => ({
      activeNode,
      activeNodeHa,
      activeNodeChangedElsewhere: changedElsewhere?.node ?? null,
      adoptActiveNodeChangedElsewhere,
      nodes,
      syncGroups,
      syncGroupsLoaded,
      loading,
      refresh,
      refreshNodes,
      refreshSyncGroups,
      applySyncGroups,
      activate,
      deleteNode,
    }),
    [
      activeNode,
      activeNodeHa,
      changedElsewhere,
      adoptActiveNodeChangedElsewhere,
      nodes,
      syncGroups,
      syncGroupsLoaded,
      loading,
      refresh,
      refreshNodes,
      refreshSyncGroups,
      applySyncGroups,
      activate,
      deleteNode,
    ],
  )

  return <NodeContext.Provider value={value}>{children}</NodeContext.Provider>
}

export function useNode() {
  const ctx = useContext(NodeContext)
  if (!ctx) throw new Error('useNode must be used within NodeProvider')
  return ctx
}
