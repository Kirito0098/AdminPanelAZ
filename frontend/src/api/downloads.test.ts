import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { clearAccessToken, setAccessToken } from '@/lib/accessToken'
import * as webSession from '@/lib/webSession'
import { downloadAwg2Backup } from './awg2'
import { downloadConfigsExport, downloadProfile, fetchQrBlob } from './configs'
import { downloadActionLogsExport } from './logs'
import { downloadBackup } from './maintenance'

function sessionExpired(): Response {
  return new Response(JSON.stringify({ detail: 'Неверный токен авторизации' }), {
    status: 401,
    headers: { 'Content-Type': 'application/json' },
  })
}

function refreshed(): Response {
  return new Response(JSON.stringify({ access_token: 'new-jwt' }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function stubFetch(...responses: Response[]) {
  const fetchMock = vi.fn()
  for (const response of responses) fetchMock.mockResolvedValueOnce(response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const downloads: Array<[string, () => Promise<Response>, string]> = [
  ['profile', () => downloadProfile(5, 'client one.ovpn'), '/api/configs/5/download?path=client%20one.ovpn'],
  ['configs CSV', () => downloadConfigsExport(), '/api/configs/export'],
  ['action logs CSV', () => downloadActionLogsExport(), '/api/logs/action-logs/export'],
  ['panel backup', () => downloadBackup('backup 1.tar.gz'), '/api/backups/backup%201.tar.gz/download'],
  ['AWG2 backup', () => downloadAwg2Backup(), '/api/awg2/backup'],
]

describe('downloads renew an expired session', () => {
  beforeEach(() => {
    setAccessToken('old-jwt')
    vi.spyOn(webSession, 'getWebSessionId').mockReturnValue(null)
  })

  afterEach(() => {
    clearAccessToken()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it.each(downloads)('%s: refreshes once on 401 and returns the file', async (_name, download, url) => {
    const fetchMock = stubFetch(sessionExpired(), refreshed(), new Response('file-bytes', { status: 200 }))

    const response = await download()

    await expect(response.text()).resolves.toBe('file-bytes')
    expect(fetchMock.mock.calls.map((call) => String(call[0]))).toEqual([url, '/api/auth/refresh', url])
    expect(new Headers(fetchMock.mock.calls[2][1].headers).get('Authorization')).toBe('Bearer new-jwt')
  })

  it.each(downloads)('%s: an error answer throws ApiError with the server message', async (_name, download) => {
    stubFetch(new Response(JSON.stringify({ detail: 'Файл не найден' }), { status: 404 }))

    await expect(download()).rejects.toMatchObject({ status: 404, message: 'Файл не найден' })
  })

  it('QR: refreshes once on 401 and returns the image with its mode', async () => {
    const fetchMock = stubFetch(
      sessionExpired(),
      refreshed(),
      new Response('png', {
        status: 200,
        headers: { 'X-Qr-Content': 'download-link', 'X-Qr-Download-Url': 'https://panel.example/d/abc' },
      }),
    )

    const result = await fetchQrBlob(5, 'client.ovpn')

    expect(result.contentMode).toBe('download-link')
    expect(result.downloadUrl).toBe('https://panel.example/d/abc')
    await expect(result.blob.text()).resolves.toBe('png')
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('AWG2 backup stays a POST', async () => {
    const fetchMock = stubFetch(new Response('tar', { status: 200 }))

    await downloadAwg2Backup()

    expect(fetchMock.mock.calls[0][1].method).toBe('POST')
  })
})
