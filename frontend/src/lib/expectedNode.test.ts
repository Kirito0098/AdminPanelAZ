import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  EXPECTED_NODE_HEADER,
  applyExpectedNodeHeader,
  createActiveNodeTracker,
  decideActiveNodeRefresh,
  getExpectedNodeId,
  isActiveNodeChangedPayload,
  notifyActiveNodeChanged,
  onActiveNodeChanged,
  setExpectedNodeId,
} from './expectedNode'
import { apiFetchAtBase } from '@/api/http'
import { apiBase } from '@/lib/panelBase'
import * as webSession from '@/lib/webSession'

afterEach(() => {
  setExpectedNodeId(null)
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('applyExpectedNodeHeader', () => {
  it('adds the node shown in the tab to write requests', () => {
    setExpectedNodeId(7)
    for (const method of ['POST', 'put', 'PATCH', 'DELETE']) {
      const headers = new Headers()
      applyExpectedNodeHeader(headers, method)
      expect(headers.get(EXPECTED_NODE_HEADER)).toBe('7')
    }
  })

  it('leaves reads and unknown node alone', () => {
    setExpectedNodeId(7)
    for (const method of [undefined, 'GET', 'head', 'OPTIONS']) {
      const headers = new Headers()
      applyExpectedNodeHeader(headers, method)
      expect(headers.has(EXPECTED_NODE_HEADER)).toBe(false)
    }
    setExpectedNodeId(null)
    const headers = new Headers()
    applyExpectedNodeHeader(headers, 'POST')
    expect(headers.has(EXPECTED_NODE_HEADER)).toBe(false)
  })

  it('keeps an explicitly set header', () => {
    setExpectedNodeId(7)
    const headers = new Headers({ [EXPECTED_NODE_HEADER]: '3' })
    applyExpectedNodeHeader(headers, 'POST')
    expect(headers.get(EXPECTED_NODE_HEADER)).toBe('3')
  })
})

describe('active node changed notifications', () => {
  it('recognises the server payload', () => {
    expect(isActiveNodeChangedPayload({ detail: { code: 'active_node_changed', message: 'x' } })).toBe(true)
    expect(isActiveNodeChangedPayload({ detail: { code: 'other' } })).toBe(false)
    expect(isActiveNodeChangedPayload({ detail: 'active_node_changed' })).toBe(false)
    expect(isActiveNodeChangedPayload(undefined)).toBe(false)
  })

  it('notifies subscribers until they unsubscribe', () => {
    const listener = vi.fn()
    const unsubscribe = onActiveNodeChanged(listener)
    notifyActiveNodeChanged()
    unsubscribe()
    notifyActiveNodeChanged()
    expect(listener).toHaveBeenCalledTimes(1)
  })
})

describe('decideActiveNodeRefresh', () => {
  it('shows the server node when the tab has none or the same one', () => {
    expect(decideActiveNodeRefresh(null, 5)).toBe('show')
    expect(decideActiveNodeRefresh(5, 5)).toBe('show')
    expect(decideActiveNodeRefresh(5, null)).toBe('show')
  })

  it('does not silently switch a tab when the node changed elsewhere', () => {
    expect(decideActiveNodeRefresh(5, 6)).toBe('changed-elsewhere')
  })
})

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('apiFetchAtBase and the expected node', () => {
  beforeEach(() => {
    vi.spyOn(webSession, 'getWebSessionId').mockReturnValue(null)
  })

  it('sends the header on panel writes only', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, {}))
    vi.stubGlobal('fetch', fetchMock)
    setExpectedNodeId(4)

    await apiFetchAtBase(apiBase, '/config-tags', { method: 'POST', body: '{}' })
    await apiFetchAtBase(apiBase, '/config-tags')
    await apiFetchAtBase('https://elsewhere.example/api', '/x', { method: 'POST', body: '{}' })

    const sent = fetchMock.mock.calls.map((call) => new Headers((call as unknown as [string, RequestInit])[1].headers))
    expect(sent[0].get(EXPECTED_NODE_HEADER)).toBe('4')
    expect(sent[1].has(EXPECTED_NODE_HEADER)).toBe(false)
    expect(sent[2].has(EXPECTED_NODE_HEADER)).toBe(false)
    expect(getExpectedNodeId()).toBe(4)
  })

  it('reports a node switched elsewhere and surfaces the server message', async () => {
    const detail = { code: 'active_node_changed', message: 'Активный узел сменился на «B»', active_node_id: 2 }
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(409, { detail })))
    const listener = vi.fn()
    const unsubscribe = onActiveNodeChanged(listener)
    setExpectedNodeId(1)

    await expect(apiFetchAtBase(apiBase, '/config-tags', { method: 'POST', body: '{}' })).rejects.toMatchObject({
      status: 409,
      message: 'Активный узел сменился на «B»',
    })
    unsubscribe()
    expect(listener).toHaveBeenCalledTimes(1)
  })

  it('does not report other conflicts', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(409, { detail: 'doall.sh уже выполняется' })))
    const listener = vi.fn()
    const unsubscribe = onActiveNodeChanged(listener)

    await expect(apiFetchAtBase(apiBase, '/settings/run-doall', { method: 'POST' })).rejects.toMatchObject({
      status: 409,
    })
    unsubscribe()
    expect(listener).not.toHaveBeenCalled()
  })
})

describe('createActiveNodeTracker', () => {
  it('shows the node and names it in write requests', () => {
    const tracker = createActiveNodeTracker()
    tracker.show(3)
    expect(getExpectedNodeId()).toBe(3)
    expect(tracker.classifyRefresh(tracker.beginRefresh(), 3)).toBe('show')
    expect(tracker.classifyRefresh(tracker.beginRefresh(), 4)).toBe('changed-elsewhere')
    tracker.show(null)
    expect(getExpectedNodeId()).toBeNull()
    expect(tracker.classifyRefresh(tracker.beginRefresh(), 4)).toBe('show')
  })

  it('drops polls that overlap an activation from this tab', () => {
    const tracker = createActiveNodeTracker()
    tracker.show(1)
    const beforeActivation = tracker.beginRefresh()
    tracker.beginActivation()
    const duringActivation = tracker.beginRefresh()
    tracker.finishActivation(2)

    expect(getExpectedNodeId()).toBe(2)
    expect(tracker.classifyRefresh(beforeActivation, 1)).toBe('stale')
    expect(tracker.classifyRefresh(duringActivation, 1)).toBe('stale')
    expect(tracker.classifyRefresh(tracker.beginRefresh(), 2)).toBe('show')
    expect(tracker.classifyRefresh(tracker.beginRefresh(), 1)).toBe('changed-elsewhere')
  })

  it('drops a poll answered while the activation is still in flight', () => {
    const tracker = createActiveNodeTracker()
    tracker.show(1)
    const beforeActivation = tracker.beginRefresh()
    tracker.beginActivation()

    expect(tracker.classifyRefresh(beforeActivation, 2)).toBe('stale')
  })

  it('keeps working after a failed activation', () => {
    const tracker = createActiveNodeTracker()
    tracker.show(1)
    tracker.beginActivation()

    expect(getExpectedNodeId()).toBe(1)
    expect(tracker.classifyRefresh(tracker.beginRefresh(), 1)).toBe('show')
    expect(tracker.classifyRefresh(tracker.beginRefresh(), 5)).toBe('changed-elsewhere')
  })
})
