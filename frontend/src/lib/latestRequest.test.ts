import { describe, expect, it } from 'vitest'

import { createLatestRequest, runLatest } from './latestRequest'

describe('createLatestRequest', () => {
  it('applies only the answer to the latest request', () => {
    const requests = createLatestRequest<number | null>(1)
    const first = requests.begin()
    const second = requests.begin()

    expect(first()).toBe(false)
    expect(second()).toBe(true)
  })

  it('drops a late answer about the previous node', () => {
    const requests = createLatestRequest<number | null>(1)
    const forNode1 = requests.begin(1)
    requests.reset(2)
    const forNode2 = requests.begin(2)

    expect(forNode1()).toBe(false)
    expect(forNode2()).toBe(true)
  })

  it('drops answers to requests that were not followed by a newer one when the node changes', () => {
    const requests = createLatestRequest<number | null>(1)
    const forNode1 = requests.begin()
    requests.reset(null)

    expect(forNode1()).toBe(false)
  })

  it('does not let a request for a node no longer shown push out the current one', () => {
    const requests = createLatestRequest<number | null>(2)
    const forNode2 = requests.begin(2)
    const forNode1 = requests.begin(1)

    expect(forNode1()).toBe(false)
    expect(forNode2()).toBe(true)
  })
})

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (err: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function recorder() {
  const calls: string[] = []
  return {
    calls,
    handlers: {
      apply: (value: string) => calls.push(`apply:${value}`),
      fail: (err: unknown) => calls.push(`fail:${err instanceof Error ? err.message : String(err)}`),
      settle: () => calls.push('settle'),
    },
  }
}

describe('runLatest', () => {
  it('applies the answer, or the error, and settles', async () => {
    const requests = createLatestRequest<number | null>(1)
    const ok = recorder()
    await runLatest(requests, async () => 'mode of node 1', ok.handlers)
    expect(ok.calls).toEqual(['apply:mode of node 1', 'settle'])

    const failing = recorder()
    await runLatest(
      requests,
      async () => {
        throw new Error('offline')
      },
      failing.handlers,
    )
    expect(failing.calls).toEqual(['fail:offline', 'settle'])
  })

  it('ignores a late answer about the previous node, including its error and loading flag', async () => {
    const requests = createLatestRequest<number | null>(1)
    const node1 = deferred<string>()
    const node1Failing = deferred<string>()
    const first = recorder()
    const second = recorder()
    const pending = [
      runLatest(requests, () => node1.promise, first.handlers),
      runLatest(requests, () => node1Failing.promise, second.handlers),
    ]

    requests.reset(2)
    const third = recorder()
    const current = runLatest(requests, async () => 'mode of node 2', third.handlers)
    node1.resolve('mode of node 1')
    node1Failing.reject(new Error('offline'))
    await Promise.all([...pending, current])

    expect(first.calls).toEqual([])
    expect(second.calls).toEqual([])
    expect(third.calls).toEqual(['apply:mode of node 2', 'settle'])
  })

  it('lets only the newest of two overlapping requests settle', async () => {
    const requests = createLatestRequest<number | null>(1)
    const older = deferred<string>()
    const olderCalls = recorder()
    const newerCalls = recorder()
    const olderRun = runLatest(requests, () => older.promise, olderCalls.handlers)
    const newerRun = runLatest(requests, async () => 'new', newerCalls.handlers)
    await newerRun
    older.resolve('old')
    await olderRun

    expect(olderCalls.calls).toEqual([])
    expect(newerCalls.calls).toEqual(['apply:new', 'settle'])
  })
})
