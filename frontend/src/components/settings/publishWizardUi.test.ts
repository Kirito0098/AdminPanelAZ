import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/client'
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
      { server_primary_ip: '127.0.0.1' } as never,
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

  it('uses uvicorn backend port even when LE cert exists', () => {
    const url = guessPublishAccessUrl(
      'uvicorn_le',
      'example.com',
      '5050',
      '443',
      {
        ssl_cert_suggestions: [
          {
            source: 'letsencrypt',
            cert: '/etc/letsencrypt/live/example.com/fullchain.pem',
            key: '/etc/letsencrypt/live/example.com/privkey.pem',
            label: 'LE',
          },
        ],
      } as never,
      true,
    )
    expect(url).toBe('https://example.com:5050/')
  })
})
