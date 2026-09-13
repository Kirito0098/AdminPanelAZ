/** Canonical GitHub docs for in-panel «Инструкция» links. */
export const DOCS_BASE =
  'https://github.com/Kirito0098/AdminPanelAZ/blob/main/docs'

export function docsUrl(path: string): string {
  const clean = path.replace(/^\/+/, '')
  return `${DOCS_BASE}/${clean}`
}

export const DOCS = {
  index: docsUrl('README.md'),
  configurations: docsUrl('konfiguracii.md'),
  noc: docsUrl('noc-monitoring.md'),
  traffic: docsUrl('traffic-monitoring.md'),
  routing: docsUrl('routing-cidr.md'),
  antizapretConfig: docsUrl('antizapret-config.md'),
  proxyNodes: docsUrl('proxy-nodes.md'),
  proxyAgent: docsUrl('proxy-agent.md'),
  warper: docsUrl('warper.md'),
  awg2: docsUrl('awg2.md'),
  telegram: docsUrl('Telegram.md'),
  editFiles: docsUrl('edit-files.md'),
  logs: docsUrl('logs.md'),
  serverMonitor: docsUrl('server-monitor.md'),
  nodes: docsUrl('uzly.md'),
  nodeSsh: docsUrl('node-ssh-transport.md'),
  nodeSync: docsUrl('NodeSync.md'),
  geoIp: docsUrl('GeoIP.md'),
  subscription: docsUrl('podpiska.md'),
  settings: docsUrl('nastrojki/README.md'),
  profile: docsUrl('nastrojki/profil.md'),
  users: docsUrl('nastrojki/polzovateli.md'),
  security: docsUrl('nastrojki/bezopasnost.md'),
  configDelivery: docsUrl('nastrojki/razdacha-konfigov.md'),
  maintenance: docsUrl('nastrojki/obsluzhivanie.md'),
  publish: docsUrl('nastrojki/set-i-publikaciya.md'),
  backup: docsUrl('nastrojki/rezervnye-kopii.md'),
  monitoringAlerts: docsUrl('nastrojki/monitoring-i-alerty.md'),
  modules: docsUrl('nastrojki/moduli.md'),
  updates: docsUrl('nastrojki/obnovleniya.md'),
  panelOps: docsUrl('nastrojki/perezapusk-i-peresborka.md'),
  diagnostics: docsUrl('nastrojki/diagnostika.md'),
} as const

/** AntiZapret upstream: proxy.sh setup (not panel docs). */
export const AZ_PROXY_SH_DOCS_URL =
  'https://github.com/GubernievS/AntiZapret-VPN#настроить-прокси-сервер'

export const FEEDBACK_URL = 'https://claymore0098.fider.io/'
