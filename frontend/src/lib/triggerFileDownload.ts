/** Force a download whose extension comes from `filename`, not the blob MIME type.
 *
 * Safari / iOS WebView map `text/plain` to `.txt` even when `<a download>` has
 * `.ovpn` / `.conf`. `application/octet-stream` keeps the given name.
 */
export function triggerFileDownload(data: Blob | ArrayBuffer | string, filename: string): void {
  const blob =
    data instanceof Blob && data.type === 'application/octet-stream'
      ? data
      : new Blob([data], { type: 'application/octet-stream' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
