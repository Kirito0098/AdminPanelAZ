// @vitest-environment jsdom
import { act, cleanup, render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/http'
import { adminUser, nodeState, notify, resetNodeState } from '@/test/nodePageHarness'
import type { NodeHaContext, User } from '@/types'
import HaScopeEnforcer from './HaScopeEnforcer'

const auth = vi.hoisted(() => ({ user: null as User | null }))

vi.mock('@/context/AuthContext', () => ({ useAuth: () => auth }))
vi.mock('@/context/NodeContext', async () => (await import('@/test/nodePageHarness')).nodeContextModule)
vi.mock('@/context/NotificationContext', async () => (await import('@/test/nodePageHarness')).notificationModule)

const regularUser = { ...adminUser, id: 8, username: 'user', role: 'user' } as User

const replicaHa: NodeHaContext = {
  sync_group_id: 3,
  group_name: 'Группа',
  shared_domain: 'vpn.example.com',
  role: 'replica',
  primary_node_id: 2,
  primary_node_name: 'primary-1',
  sync_mode: 'push',
  sync_status: 'synced',
}

function enforcer() {
  return (
    <MemoryRouter initialEntries={['/']}>
      <HaScopeEnforcer />
    </MemoryRouter>
  )
}

async function mountOnReplica() {
  Object.assign(nodeState, { loading: false, activeNodeHa: { ...replicaHa } })
  const result = render(enforcer())
  await act(async () => {})
  return result
}

describe('HaScopeEnforcer', () => {
  beforeEach(() => {
    resetNodeState()
    nodeState.activate.mockReset()
    auth.user = adminUser
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('does not try to switch for a non-admin and shows nothing', async () => {
    auth.user = regularUser
    nodeState.activate.mockRejectedValue(new ApiError('Доступ запрещён (403).', 403))

    await mountOnReplica()

    expect(nodeState.activate).not.toHaveBeenCalled()
    expect(notify.info).not.toHaveBeenCalled()
    expect(notify.warning).not.toHaveBeenCalled()
    expect(notify.error).not.toHaveBeenCalled()
  })

  it('switches a replica to its primary and says so', async () => {
    nodeState.activate.mockResolvedValue(undefined)

    await mountOnReplica()

    expect(nodeState.activate).toHaveBeenCalledWith(2)
    expect(notify.info).toHaveBeenCalledWith('HA: переключено на primary «primary-1»')
  })

  it('explains a refused switch (403) for an admin instead of an unhandled error', async () => {
    nodeState.activate.mockRejectedValue(new ApiError('Доступ запрещён (403).', 403))

    await mountOnReplica()

    expect(notify.warning).toHaveBeenCalledWith(
      'HA: нет прав переключиться на primary «primary-1», страница показывает данные реплики',
    )
    expect(notify.info).not.toHaveBeenCalled()
  })

  it('shows the server message for other failures', async () => {
    nodeState.activate.mockRejectedValue(new ApiError('Узел не отвечает', 502))

    await mountOnReplica()

    expect(notify.error).toHaveBeenCalledWith(
      'HA: не удалось переключиться на primary «primary-1»: Узел не отвечает',
    )
  })

  it('does not retry the same primary on every node poll after a failure', async () => {
    nodeState.activate.mockRejectedValue(new ApiError('Доступ запрещён (403).', 403))
    const result = await mountOnReplica()

    nodeState.activeNodeHa = { ...replicaHa }
    result.rerender(enforcer())
    await act(async () => {})

    expect(nodeState.activate).toHaveBeenCalledTimes(1)
    expect(notify.warning).toHaveBeenCalledTimes(1)
  })
})
