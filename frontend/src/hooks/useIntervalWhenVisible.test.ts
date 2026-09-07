import { describe, expect, it } from 'vitest'

import { isDocumentHidden } from './useIntervalWhenVisible'

describe('isDocumentHidden', () => {
  it('returns a boolean without throwing when document exists', () => {
    expect(typeof isDocumentHidden()).toBe('boolean')
  })
})
