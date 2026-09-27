import { act, render, type RenderResult } from '@testing-library/react'
import type { ReactElement, ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

import type { Node, NodeHaContext, User } from '@/types'

/**
 * Shared state and module stubs for page tests that load data keyed on the active node.
 * Use from `vi.mock` factories via dynamic import, e.g.
 * `vi.mock('@/context/NodeContext', async () => (await import('@/test/nodePageHarness')).nodeContextModule)`.
 */

export const adminUser = { id: 7, username: 'admin', role: 'admin', theme: 'dark', is_active: true } as User
export const testNode = { id: 1, name: 'main', status: 'online', is_local: true } as unknown as Node

export const nodeState = {
  activeNode: null as Node | null,
  activeNodeHa: null as NodeHaContext | null,
  nodes: [] as Node[],
  loading: true,
  nodesLoading: true,
  activate: vi.fn(),
}

export function resetNodeState() {
  Object.assign(nodeState, { activeNode: null, activeNodeHa: null, nodes: [], loading: true, nodesLoading: true })
}

export const notify = { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }
export const progress = {
  startGlobal: vi.fn(),
  doneGlobal: vi.fn(),
  withInline: vi.fn(),
  trackBackgroundTask: vi.fn(),
  inline: false,
}
const featureModules = { isEnabled: () => true }
const auth = { user: adminUser }

export const nodeContextModule = { useNode: () => nodeState }
export const notificationModule = { useNotifications: () => notify }
export const progressModule = { useProgress: () => progress }
export const featureModulesModule = { useFeatureModules: () => featureModules }
export const authModule = { useAuth: () => auth }

export function TestRouter({ children }: { children: ReactNode }) {
  return <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>{children}</MemoryRouter>
}

/** Renders while NodeContext is still loading, then applies `resolved` (active node by default) and re-renders. */
export async function mountWhileActiveNodeResolves(
  page: () => ReactElement,
  resolved: Partial<typeof nodeState> = {},
): Promise<RenderResult> {
  const result = render(<TestRouter>{page()}</TestRouter>)
  await act(async () => {})
  Object.assign(nodeState, { activeNode: testNode, loading: false, nodesLoading: false, ...resolved })
  result.rerender(<TestRouter>{page()}</TestRouter>)
  await act(async () => {})
  return result
}

/** Re-renders after changing NodeContext state (e.g. the node list arriving later). */
export async function updateNodeState(result: RenderResult, page: () => ReactElement, next: Partial<typeof nodeState>) {
  Object.assign(nodeState, next)
  result.rerender(<TestRouter>{page()}</TestRouter>)
  await act(async () => {})
}
