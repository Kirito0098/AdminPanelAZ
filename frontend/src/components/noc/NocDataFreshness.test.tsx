// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import NocDataFreshness from './NocDataFreshness'

const originalTz = process.env.TZ

describe('NocDataFreshness', () => {
  beforeAll(() => {
    process.env.TZ = 'Europe/Moscow'
  })

  afterAll(() => {
    if (originalTz === undefined) delete process.env.TZ
    else process.env.TZ = originalTz
  })

  afterEach(cleanup)

  it('treats a naive backend timestamp as UTC', () => {
    const naiveUtc = new Date(Date.now() - 5000).toISOString().replace('Z', '')

    render(<NocDataFreshness timestamp={naiveUtc} refreshIntervalSec={30} />)

    expect(screen.getByText(/^данные \d+с назад$/)).toBeTruthy()
    expect(screen.queryByText(/stale/)).toBeNull()
  })

  it('marks old data as stale', () => {
    const naiveUtc = new Date(Date.now() - 5 * 60_000).toISOString().replace('Z', '')

    render(<NocDataFreshness timestamp={naiveUtc} refreshIntervalSec={30} />)

    expect(screen.getByText('stale · 5м назад')).toBeTruthy()
  })
})
