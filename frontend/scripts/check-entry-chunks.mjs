#!/usr/bin/env node
// Fails the build check when chart code (recharts) is loaded eagerly by index.html,
// i.e. on every page including /login, or by a page whose charts are not its main content;
// and when words revealing a VPN panel are visible without login (page, eager chunks, asset names).
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { dirname, join, posix } from 'node:path'
import { fileURLToPath } from 'node:url'

const CHART_MARKER = 'recharts-surface'
const CHART_PAGES = new Set(['MonitoringPage', 'ServerMonitorPage'])
const HTML_CHUNK_RE = /(?:src|href)="\.\/([^"]+\.js)"/g
const STATIC_IMPORT_RE = /(?:\bfrom|\bimport)\s*["']\.\/([^"']+\.js)["']/g
const PAGE_SOURCE_RE = /^src\/pages\/([A-Z][A-Za-z0-9]*Page)\.tsx$/
// Words that tell an anonymous visitor what the server is for; first match per place is reported.
const STOP_WORDS = [
  ['antizapret', /anti-?zapret|антизапрет/i],
  ['zapret', /zapret/i],
  ['openvpn', /openvpn/i],
  ['vpn', /vpn/i],
  ['wireguard', /wireguard/i],
  ['amnezia', /amnezia/i],
  ['awg', /(?<![a-z0-9])awg/i],
  ['warp', /(?<![a-z0-9])warp(?![a-z])|warper/i],
  ['xray', /(?<![a-z0-9])xray/i],
  ['proxy', /(?<![A-Za-z0-9])proxy(?![A-Za-z0-9])|прокси/],
  ['tunnel', /tunnel|туннел/i],
]

/** The given chunks plus everything they import statically (dynamic import() is not followed). */
export function staticClosure(distDir, roots) {
  const pending = roots.map((chunk) => posix.normalize(chunk))
  const seen = new Set()
  while (pending.length > 0) {
    const chunk = pending.pop()
    if (seen.has(chunk)) continue
    seen.add(chunk)
    const file = join(distDir, chunk)
    if (!existsSync(file)) continue
    const code = readFileSync(file, 'utf8')
    for (const m of code.matchAll(STATIC_IMPORT_RE)) {
      pending.push(posix.join(posix.dirname(chunk), m[1]))
    }
  }
  return [...seen].sort()
}

/** Chunks loaded before any route renders: entry script, modulepreloads and their static imports. */
export function eagerChunks(distDir) {
  const html = readFileSync(join(distDir, 'index.html'), 'utf8')
  return staticClosure(
    distDir,
    [...html.matchAll(HTML_CHUNK_RE)].map((m) => m[1]),
  )
}

function withChartCode(distDir, chunks) {
  return chunks.filter((chunk) => {
    const file = join(distDir, chunk)
    return existsSync(file) && readFileSync(file, 'utf8').includes(CHART_MARKER)
  })
}

export function eagerChartChunks(distDir) {
  return withChartCode(distDir, eagerChunks(distDir))
}

/** Route chunks, other than the chart pages, that pull chart code as soon as they open. */
export function pagesWithChartCode(distDir) {
  const manifestFile = join(distDir, '.vite', 'manifest.json')
  if (!existsSync(manifestFile)) return []
  const manifest = JSON.parse(readFileSync(manifestFile, 'utf8'))
  return Object.entries(manifest)
    .map(([src, entry]) => ({ file: entry.file, page: PAGE_SOURCE_RE.exec(src)?.[1] }))
    .filter(({ page }) => page && !CHART_PAGES.has(page))
    .filter(({ file }) => withChartCode(distDir, staticClosure(distDir, [file])).length > 0)
    .map(({ page }) => page)
    .sort()
}

function firstStopWord(text) {
  return STOP_WORDS.find(([, re]) => re.test(text))?.[0]
}

/** Stop words an anonymous visitor can see: index.html, eager chunks, and every asset file name. */
export function publicWordLeaks(distDir) {
  const leaks = []
  const check = (where, text) => {
    const word = firstStopWord(text)
    if (word) leaks.push({ where, word })
  }
  check('index.html', readFileSync(join(distDir, 'index.html'), 'utf8'))
  for (const chunk of eagerChunks(distDir)) {
    const file = join(distDir, chunk)
    if (existsSync(file)) check(chunk, readFileSync(file, 'utf8'))
  }
  const assets = join(distDir, 'assets')
  if (existsSync(assets)) {
    for (const name of readdirSync(assets).sort()) check(`assets/${name} (file name)`, name)
  }
  return leaks
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const distDir = process.argv[2] ?? join(dirname(fileURLToPath(import.meta.url)), '..', 'dist')
  const eager = eagerChartChunks(distDir)
  const pages = pagesWithChartCode(distDir)
  if (eager.length > 0) console.error(`recharts is loaded on every page via: ${eager.join(', ')}`)
  if (pages.length > 0) console.error(`recharts is loaded up front by: ${pages.join(', ')} (lazy-load the chart)`)
  const leaks = publicWordLeaks(distDir)
  for (const { where, word } of leaks) console.error(`"${word}" is visible without login in ${where}`)
  if (eager.length > 0 || pages.length > 0 || leaks.length > 0) process.exit(1)
  console.log(
    `ok: ${eagerChunks(distDir).length} eager chunks, no chart code outside ${[...CHART_PAGES].join(', ')}, no stop words without login`,
  )
}
