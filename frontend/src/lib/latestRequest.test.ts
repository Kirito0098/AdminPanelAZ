import { describe, expect, it } from 'vitest'

import { createLatestRequest } from './latestRequest'

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
