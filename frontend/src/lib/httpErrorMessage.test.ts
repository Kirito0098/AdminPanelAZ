import { describe, expect, it } from 'vitest'
import { normalizeHttpErrorDetail, parseHttpErrorBody } from './httpErrorMessage'

const NGINX_502 = `<html>
<head><title>502 Bad Gateway</title></head>
<body>
<center><h1>502 Bad Gateway</h1></center>
<hr><center>nginx/1.24.0 (Ubuntu)</center>
</body>
</html>`

describe('httpErrorMessage', () => {
  it('converts nginx html 502 to friendly message', () => {
    const msg = parseHttpErrorBody(NGINX_502, 502)
    expect(msg).toContain('502')
    expect(msg).not.toContain('<html')
    expect(msg).toContain('перезапуск')
  })

  it('converts nginx html 404 to friendly message', () => {
    const msg = parseHttpErrorBody('<html><title>404 Not Found</title></html>', 404)
    expect(msg).toContain('404')
    expect(msg).not.toContain('<html')
  })

  it('keeps json detail strings', () => {
    const msg = parseHttpErrorBody(JSON.stringify({ detail: 'Домен уже занят' }), 400)
    expect(msg).toBe('Домен уже занят')
  })

  it('truncates very long plain text', () => {
    const long = 'x'.repeat(500)
    const msg = normalizeHttpErrorDetail(long, 500)
    expect(msg.length).toBeLessThan(410)
    expect(msg.endsWith('…')).toBe(true)
  })
})
