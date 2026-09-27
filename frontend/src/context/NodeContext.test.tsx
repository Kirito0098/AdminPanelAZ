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
const node = { id: 1, name: 'main', status: 'online', is_local: true } as unknown as Node

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
})
