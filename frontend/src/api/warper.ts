import {
  API_BASE,
  apiFetch,
  getToken,
} from './http'

export async function getWarperHealth() {
  return apiFetch<import('../types').WarperHealthResponse>('/warper/health')
}

export async function getWarperStatus() {
  return apiFetch<import('../types').WarperStatusResponse>('/warper/status')
}

export async function getWarperDoctor() {
  return apiFetch<import('../types').WarperDoctorResponse>('/warper/doctor')
}

export async function postWarperToggle() {
  return apiFetch<import('../types').WarperActionResponse>('/warper/toggle', { method: 'POST' })
}

export async function getWarperDomains() {
  return apiFetch<import('../types').WarperDomainsResponse>('/warper/domains')
}

export async function setWarperDomainList(name: string, enable: boolean) {
  return apiFetch<import('../types').WarperActionResponse>(`/warper/domains/lists/${encodeURIComponent(name)}`, {
    method: 'POST',
    body: JSON.stringify({ enable }),
  })
}

export async function saveWarperUserDomainsText(text: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/domains/text', {
    method: 'PUT',
    body: JSON.stringify({ text }),
  })
}

export async function getWarperIpRanges() {
  return apiFetch<import('../types').WarperIpRangesResponse>('/warper/ip-ranges')
}

export async function setWarperIpRouteMode(mode: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/ip-ranges/mode', {
    method: 'POST',
    body: JSON.stringify({ mode }),
  })
}

export async function setWarperIpExport(enable: boolean) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/ip-ranges/export', {
    method: 'POST',
    body: JSON.stringify({ enable }),
  })
}

export async function saveWarperIpRangesText(text: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/ip-ranges/text', {
    method: 'PUT',
    body: JSON.stringify({ text }),
  })
}

export async function getWarperTraffic(period: import('../types').WarperTrafficPeriod = 'today') {
  return apiFetch<import('../types').WarperTrafficResponse>(`/warper/traffic?period=${encodeURIComponent(period)}`)
}

export async function getWarperLogs(lines = 200) {
  return apiFetch<import('../types').WarperLogsResponse>(`/warper/logs?lines=${lines}`)
}

export async function getWarperMode() {
  return apiFetch<import('../types').WarperModeResponse>('/warper/settings/mode')
}

export async function getWarperSettingsOptions() {
  return apiFetch<import('../types').WarperSettingsOptionsResponse>('/warper/settings/options')
}

export async function setWarperModeWarp(keySource?: 'system' | 'wgcf' | 'root' | 'generate' | null) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/mode/warp', {
    method: 'POST',
    body: JSON.stringify({ key_source: keySource ?? null }),
  })
}

export async function setWarperModeSlave(host: string, port: number, key: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/mode/slave', {
    method: 'POST',
    body: JSON.stringify({ host, port, key }),
  })
}

export async function setWarperModeSlaveLink(link: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/mode/slave', {
    method: 'POST',
    body: JSON.stringify({ link }),
  })
}

export async function setWarperModeWg(configPath: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/mode/wg', {
    method: 'POST',
    body: JSON.stringify({ config_path: configPath }),
  })
}

export async function setWarperModeVless(link: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/mode/vless', {
    method: 'POST',
    body: JSON.stringify({ link }),
  })
}

export async function setWarperModeHy2(link: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/mode/hy2', {
    method: 'POST',
    body: JSON.stringify({ link }),
  })
}

export async function setWarperModeOpenVpn(configPath: string, username?: string | null, password?: string | null) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/mode/openvpn', {
    method: 'POST',
    body: JSON.stringify({ config_path: configPath, username: username || null, password: password || null }),
  })
}

export async function forgetWarperOvpnCredentials(configPath: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/ovpn/forget', {
    method: 'POST',
    body: JSON.stringify({ config_path: configPath }),
  })
}

export async function setWarperFullVpn(enable: boolean) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/fullvpn', {
    method: 'PUT',
    body: JSON.stringify({ enable }),
  })
}

export async function setWarperAutopatch(enable: boolean) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/autopatch', {
    method: 'PUT',
    body: JSON.stringify({ enable }),
  })
}

export async function postWarperResync() {
  return apiFetch<import('../types').WarperActionResponse>('/warper/resync', { method: 'POST' })
}

export async function postWarperUpdateLists() {
  return apiFetch<import('../types').WarperActionResponse>('/warper/domains/update-lists', { method: 'POST' })
}

export async function getWarperAutoResolve() {
  return apiFetch<import('../types').WarperAutoResolveResponse>('/warper/resolve')
}

export async function setWarperAutoResolve(enable: boolean) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/resolve', {
    method: 'PUT',
    body: JSON.stringify({ enable }),
  })
}

export async function postWarperResolveSync(force = false) {
  return apiFetch<import('../types').WarperActionResponse>(`/warper/resolve/sync${force ? '?force=true' : ''}`, {
    method: 'POST',
  })
}

export async function postWarperResolveClean(domain?: string | null) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/resolve/clean', {
    method: 'POST',
    body: JSON.stringify({ domain: domain?.trim() || null }),
  })
}

export async function getWarperIpRoutes() {
  return apiFetch<import('../types').WarperIpRoutesResponse>('/warper/ip-routes')
}

export async function postWarperClearIpRoutes() {
  return apiFetch<import('../types').WarperActionResponse>('/warper/ip-routes/clear', { method: 'POST' })
}

export async function getWarperSubnets() {
  return apiFetch<import('../types').WarperSubnetsResponse>('/warper/subnets')
}

export async function getWarperSingboxStatus() {
  return apiFetch<import('../types').WarperSingboxStatusResponse>('/warper/singbox/status')
}

export async function setWarperSubnet(subnet: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/subnet', {
    method: 'PUT',
    body: JSON.stringify({ subnet }),
  })
}

export async function setWarperMtu(mtu: number) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/mtu', {
    method: 'PUT',
    body: JSON.stringify({ mtu }),
  })
}

export async function setWarperLogLevel(level: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/settings/log-level', {
    method: 'PUT',
    body: JSON.stringify({ level }),
  })
}

export async function postWarperSingbox(action: 'start' | 'stop' | 'restart' | 'enable' | 'disable' | 'upgrade') {
  return apiFetch<import('../types').WarperActionResponse>(`/warper/singbox/${action}`, { method: 'POST' })
}

export async function searchWarperCatalog(query = '') {
  const params = query.trim() ? `?query=${encodeURIComponent(query.trim())}` : ''
  return apiFetch<import('../types').WarperCatalogSearchResponse>(`/warper/catalog/search${params}`)
}

export async function getWarperCatalogInstalled() {
  return apiFetch<import('../types').WarperCatalogInstalledResponse>('/warper/catalog/installed')
}

export async function showWarperCatalog(name: string) {
  return apiFetch<import('../types').WarperCatalogShowResponse>(`/warper/catalog/show/${encodeURIComponent(name)}`)
}

export async function addWarperCatalog(name: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/catalog/add', {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
}

export async function removeWarperCatalog(name: string) {
  return apiFetch<import('../types').WarperActionResponse>('/warper/catalog/remove', {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
}

export async function updateWarperCatalog(name = '') {
  const params = name.trim() ? `?name=${encodeURIComponent(name.trim())}` : ''
  return apiFetch<import('../types').WarperActionResponse>(`/warper/catalog/update${params}`, { method: 'POST' })
}

export async function refreshWarperCatalog() {
  return apiFetch<import('../types').WarperActionResponse>('/warper/catalog/refresh', { method: 'POST' })
}

export async function checkWarperUpdates(force = false) {
  const params = force ? '?force=true' : ''
  return apiFetch<import('../types').WarperUpdatesCheckResponse>(`/warper/updates/check${params}`)
}

export function openWarperUpdateStream(
  onEvent: (event: import('../types').WarperUpdateStreamEvent) => void,
  onError?: (message: string) => void,
): EventSource | null {
  const token = getToken()
  if (!token) return null
  const url = `${API_BASE}/warper/updates/stream?token=${encodeURIComponent(token)}`
  const source = new EventSource(url)
  source.onmessage = (event) => {
    try {
      onEvent(JSON.parse(event.data) as import('../types').WarperUpdateStreamEvent)
    } catch {
      onError?.('Ошибка разбора потока обновления AZ-WARP')
    }
  }
  source.onerror = () => {
    onError?.('Соединение с потоком обновления прервано')
  }
  return source
}
