import { describe, expect, it } from 'vitest'
import { ApiError } from '@/lib/api'
import { guessPublishAccessUrl, isPublishStartTransientError } from '@/components/settings/publishWizardUi'

describe('isPublishStartTransientError', () => {
  it('treats gateway errors and network failures as transient', () => {
    expect(isPublishStartTransientError(new ApiError('bad gateway', 502))).toBe(true)
    expect(isPublishStartTransientError(new ApiError('unavailable', 503))).toBe(true)
    expect(isPublishStartTransientError(new TypeError('Failed to fetch'))).toBe(true)
  })

  it('does not treat 404 as transient', () => {
    expect(isPublishStartTransientError(new ApiError('not found', 404))).toBe(false)
  })
})

describe('guessPublishAccessUrl', () => {
  it('ignores accessPath for non-nginx modes', () => {
    const url = guessPublishAccessUrl(
      'http_direct',
      '',
      '8000',
      '443',
      null,
      null,
      '/panel',
    )
    expect(url).toBe('http://127.0.0.1:8000/')
  })

  it('includes accessPath for nginx modes', () => {
    const url = guessPublishAccessUrl(
      'nginx_le',
      'example.com',
      '8000',
      '443',
      null,
      true,
      '/panel',
    )
    expect(url).toBe('https://example.com/panel/')
  })
})
