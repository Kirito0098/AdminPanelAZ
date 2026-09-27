import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import * as api from '@/api/client'
import { useAuth } from '@/context/AuthContext'
import { useIntervalWhenVisible } from '@/hooks/useIntervalWhenVisible'
import { createActiveNodeTracker, deleteNodeInTab, onActiveNodeChanged, refreshActiveNode } from '@/lib/expectedNode'
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
  /** ``nodes`` not yet fetched for the signed-in user (always false for non-admins once checked). */
  nodesLoading: boolean
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
  const [resolvedForUserId, setResolvedForUserId] = useState<number | null>(null)
  const [nodesResolvedForUserId, setNodesResolvedForUserId] = useState<number | null>(null)
  // Pages mount in the same render the user appears, before refresh() runs — loading must already be true then.
  const loading = user != null && resolvedForUserId !== user.id
  const nodesLoading = user != null && nodesResolvedForUserId !== user.id
  // A request started for the previous user may settle after logout → login.
  const currentUserIdRef = useRef<number | null>(null)
  currentUserIdRef.current = user?.id ?? null

  const showActiveNode = useCallback((state: ActiveNodeState) => {
    trackerRef.current.show(state.node?.id ?? null)
    setActiveNode(state.node)
    setActiveNodeHa(state.ha)
    setChangedElsewhere(null)
  }, [])

  const refresh = useCallback(async () => {
    if (!user) {
      showActiveNode({ node: null, ha: null })
      setResolvedForUserId(null)
      return
    }
    const isCurrentUser = () => currentUserIdRef.current === user.id
    try {
      const result = await refreshActiveNode(trackerRef.current, api.getActiveNode)
      if (!isCurrentUser()) return
      if (result.outcome !== 'show' && result.outcome !== 'changed-elsewhere') return
      const state = { node: result.active.node, ha: result.active.ha ?? null }
      if (result.outcome === 'changed-elsewhere') setChangedElsewhere(state)
      else showActiveNode(state)
    } finally {
      if (isCurrentUser()) setResolvedForUserId(user.id)
    }
  }, [user, showActiveNode])

  const refreshNodes = useCallback(async () => {
    if (!user || user.role !== 'admin') {
      setNodes([])
      setNodesResolvedForUserId(user?.id ?? null)
      return
    }
    const isCurrentUser = () => currentUserIdRef.current === user.id
    try {
      const list = await api.getNodes()
      if (isCurrentUser()) setNodes(list)
    } catch (err) {
      if (isCurrentUser()) setNodes([])
      throw err
    } finally {
      if (isCurrentUser()) setNodesResolvedForUserId(user.id)
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
      nodesLoading,
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
      nodesLoading,
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
