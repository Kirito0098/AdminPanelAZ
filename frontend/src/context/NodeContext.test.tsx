// @vitest-environment jsdom
import { act, cleanup, render } from '@testing-library/react'
import { useEffect } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Node, User } from '@/types'
import { NodeProvider, useNode } from './NodeContext'

const auth = vi.hoisted(() => ({ user: null as User | null }))
const api = vi.hoisted(() => ({
  getActiveNode: vi.fn(),
  getNodes: vi.fn(),
  getNodeSyncGroups: vi.fn(),
}))

vi.mock('@/context/AuthContext', () => ({ useAuth: () => auth }))
vi.mock('@/api/client', () => api)

const admin = { id: 7, username: 'admin', role: 'admin', theme: 'dark', is_active: true } as User
const otherAdmin = { ...admin, id: 8, username: 'other' } as User
const node = { id: 1, name: 'main', status: 'online', is_local: true } as unknown as Node
const staleNode = { ...node, id: 5, name: 'stale' } as Node

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

describe('NodeProvider loading', () => {
  let seen: Array<{ loading: boolean; nodeId: number | null }>

  function Probe() {
    const { loading, activeNode } = useNode()
    useEffect(() => {
      seen.push({ loading, nodeId: activeNode?.id ?? null })
    }, [loading, activeNode?.id])
    return null
  }

  beforeEach(() => {
    seen = []
    auth.user = null
    api.getNodes.mockResolvedValue([])
    api.getNodeSyncGroups.mockResolvedValue([])
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('stays loading from the render the user appears until the active node resolves', async () => {
    const active = deferred<{ node: Node; ha: null }>()
    api.getActiveNode.mockReturnValue(active.promise)

    const { rerender } = render(
      <NodeProvider>
        <Probe />
      </NodeProvider>,
    )
    await act(async () => {})
    seen = []

    auth.user = admin
    rerender(
      <NodeProvider>
        <Probe />
      </NodeProvider>,
    )
    await act(async () => {})

    expect(seen).toEqual([{ loading: true, nodeId: null }])

    await act(async () => {
      active.resolve({ node, ha: null })
    })

    expect(seen[seen.length - 1]).toEqual({ loading: false, nodeId: 1 })
    expect(seen.filter((s) => !s.loading)).toEqual([{ loading: false, nodeId: 1 }])
  })

  it('does not go back to loading when the same user is re-read', async () => {
    api.getActiveNode.mockResolvedValue({ node, ha: null })
    auth.user = admin
    const { rerender } = render(
      <NodeProvider>
        <Probe />
      </NodeProvider>,
    )
    await act(async () => {})
    expect(seen[seen.length - 1]).toEqual({ loading: false, nodeId: 1 })
    seen = []

    auth.user = { ...admin }
    rerender(
      <NodeProvider>
        <Probe />
      </NodeProvider>,
    )
    await act(async () => {})

    expect(seen).toEqual([])
    expect(api.getActiveNode).toHaveBeenCalledTimes(2)
  })

  describe('after logout → login as another user', () => {
    let previousUser: ReturnType<typeof deferred<{ node: Node; ha: null }>>
    let nextUser: ReturnType<typeof deferred<{ node: Node; ha: null }>>

    function tree() {
      return (
        <NodeProvider>
          <Probe />
        </NodeProvider>
      )
    }

    async function switchUsersWhileFirstRefreshIsPending() {
      previousUser = deferred()
      nextUser = deferred()
      api.getActiveNode.mockReturnValueOnce(previousUser.promise).mockReturnValueOnce(nextUser.promise)
      auth.user = admin
      const { rerender } = render(tree())
      await act(async () => {})

      auth.user = null
      rerender(tree())
      await act(async () => {})

      auth.user = otherAdmin
      rerender(tree())
      await act(async () => {})
      expect(seen[seen.length - 1]).toEqual({ loading: true, nodeId: null })
    }

    it('ignores the previous user refresh settling first', async () => {
      await switchUsersWhileFirstRefreshIsPending()

      await act(async () => {
        previousUser.resolve({ node: staleNode, ha: null })
      })
      expect(seen[seen.length - 1]).toEqual({ loading: true, nodeId: null })

      await act(async () => {
        nextUser.resolve({ node, ha: null })
      })
      expect(seen[seen.length - 1]).toEqual({ loading: false, nodeId: 1 })
    })

    it('does not flip back to loading when the previous user refresh settles last', async () => {
      await switchUsersWhileFirstRefreshIsPending()

      await act(async () => {
        nextUser.resolve({ node, ha: null })
      })
      expect(seen[seen.length - 1]).toEqual({ loading: false, nodeId: 1 })

      await act(async () => {
        previousUser.resolve({ node: staleNode, ha: null })
      })
      expect(seen[seen.length - 1]).toEqual({ loading: false, nodeId: 1 })
    })
  })
})

describe('NodeProvider nodesLoading', () => {
  let seen: Array<{ nodesLoading: boolean; nodes: number }>

  function Probe() {
    const { nodesLoading, nodes } = useNode()
    useEffect(() => {
      seen.push({ nodesLoading, nodes: nodes.length })
    }, [nodesLoading, nodes.length])
    return null
  }

  beforeEach(() => {
    seen = []
    api.getActiveNode.mockResolvedValue({ node, ha: null })
    api.getNodeSyncGroups.mockResolvedValue([])
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('stays true for an admin until the node list arrives', async () => {
    const list = deferred<Node[]>()
    api.getNodes.mockReturnValue(list.promise)
    auth.user = admin

    render(
      <NodeProvider>
        <Probe />
      </NodeProvider>,
    )
    await act(async () => {})
    expect(seen).toEqual([{ nodesLoading: true, nodes: 0 }])

    await act(async () => {
      list.resolve([node, staleNode])
    })
    expect(seen[seen.length - 1]).toEqual({ nodesLoading: false, nodes: 2 })
    expect(seen.filter((s) => !s.nodesLoading)).toEqual([{ nodesLoading: false, nodes: 2 }])
  })

  it('is false for a non-admin once checked', async () => {
    auth.user = { ...admin, role: 'user' } as User

    render(
      <NodeProvider>
        <Probe />
      </NodeProvider>,
    )
    await act(async () => {})

    expect(seen[seen.length - 1]).toEqual({ nodesLoading: false, nodes: 0 })
    expect(api.getNodes).not.toHaveBeenCalled()
  })
})
