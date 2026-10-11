import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  eagerChartChunks,
  eagerChunks,
  pagesWithChartCode,
  publicAssetFiles,
  publicGateProblems,
  publicWordLeaks,
} from '../../scripts/check-entry-chunks.mjs'

let dist: string

function write(name: string, content: string) {
  writeFileSync(join(dist, name), content)
}

describe('check-entry-chunks', () => {
  beforeEach(() => {
    dist = mkdtempSync(join(tmpdir(), 'dist-'))
    mkdirSync(join(dist, 'assets'))
  })

  afterEach(() => {
    rmSync(dist, { recursive: true, force: true })
  })

  it('follows the entry script, modulepreloads and their static imports, not dynamic ones', () => {
    write(
      'index.html',
      '<script type="module" src="./assets/index.js"></script><link rel="modulepreload" href="./assets/vendor.js">',
    )
    write('assets/index.js', 'import{a}from"./shared.js";import "./side.js";const p=()=>import("./Page.js")')
    write('assets/vendor.js', '')
    write('assets/shared.js', 'export const a=1')
    write('assets/side.js', '')
    write('assets/Page.js', 'import{x}from"./charts.js"')
    write('assets/charts.js', 'class="recharts-surface"')

    expect(eagerChunks(dist)).toEqual(['assets/index.js', 'assets/shared.js', 'assets/side.js', 'assets/vendor.js'])
    expect(eagerChartChunks(dist)).toEqual([])
  })

  it('reports chart code reached eagerly through a static import', () => {
    write('index.html', '<script type="module" src="./assets/index.js"></script>')
    write('assets/index.js', 'import{R}from"./recharts.js"')
    write('assets/recharts.js', 'export const R=1;const c="recharts-surface"')

    expect(eagerChartChunks(dist)).toEqual(['assets/recharts.js'])
  })

  it('reports a preloaded chart chunk and ignores preloads of missing files', () => {
    write(
      'index.html',
      '<script src="./assets/index.js"></script><link rel="modulepreload" href="./assets/charts.js"><link rel="modulepreload" href="./assets/gone.js">',
    )
    write('assets/index.js', '')
    write('assets/charts.js', 'recharts-surface')

    expect(eagerChartChunks(dist)).toEqual(['assets/charts.js'])
  })

  it('flags pages that import chart code statically, except the chart pages', () => {
    mkdirSync(join(dist, '.vite'))
    write(
      '.vite/manifest.json',
      JSON.stringify({
        'src/pages/TrafficPage.tsx': { file: 'assets/Xy-9.js' },
        'src/pages/WarperPage.tsx': { file: 'assets/Qw12.js' },
        'src/pages/MonitoringPage.tsx': { file: 'assets/Zz12.js' },
        'src/pages/ServerMonitorPage.tsx': { file: 'assets/Zz13.js' },
        'src/pages/SettingsPage.tsx': { file: 'assets/Aa12.js' },
        'src/lib/pageHelpers.ts': { file: 'assets/Cc12.js' },
      }),
    )
    write('assets/Ab_1.js', 'recharts-surface')
    write('assets/Xy-9.js', 'import{C}from"./Ab_1.js"')
    write('assets/Qw12.js', 'const C=()=>import("./Ab_1.js")')
    write('assets/Zz12.js', 'import{C}from"./Ab_1.js"')
    write('assets/Zz13.js', 'import{C}from"./Ab_1.js"')
    write('assets/Aa12.js', 'import"./Bb12.js"')
    write('assets/Bb12.js', 'import"./Ab_1.js"')
    write('assets/Cc12.js', 'import"./Ab_1.js"')

    expect(pagesWithChartCode(dist)).toEqual(['SettingsPage', 'TrafficPage'])
  })

  it('reports stop words in the page, eager chunks and any asset file name', () => {
    write('index.html', '<title>AntiZapret</title><script type="module" src="./assets/index.js"></script>')
    write('assets/index.js', 'import"./shared.js";const p=()=>import("./lazy.js")')
    write('assets/shared.js', 'const label="WireGuard"')
    write('assets/lazy.js', 'const label="OpenVPN"')
    write('assets/vpnAccess-Ab12.js', '')

    expect(publicWordLeaks(dist)).toEqual([
      { where: 'index.html', word: 'antizapret' },
      { where: 'assets/shared.js', word: 'wireguard' },
      { where: 'assets/vpnAccess-Ab12.js (file name)', word: 'vpn' },
    ])
  })

  it('finds no leaks in a neutral build', () => {
    write('index.html', '<title>Admin Panel</title><script type="module" src="./assets/Qx1.js"></script>')
    write('assets/Qx1.js', 'const p=()=>import("./Zz9.js")')
    write('assets/Zz9.js', 'const label="OpenVPN"')

    expect(publicWordLeaks(dist)).toEqual([])
  })

  it('lists the login and portal pages with their static imports as public files', () => {
    mkdirSync(join(dist, '.vite'))
    write(
      '.vite/manifest.json',
      JSON.stringify({
        'index.html': {
          file: 'assets/e1.js',
          css: ['assets/s1.css'],
          imports: ['_sh.js'],
          dynamicImports: ['_shell.js', 'src/pages/PortalPage.tsx'],
        },
        '_sh.js': { file: 'assets/sh.js' },
        'src/pages/PortalPage.tsx': { file: 'assets/p1.js', imports: ['index.html', '_sh.js'], assets: ['assets/logo.svg'] },
        '_shell.js': { file: 'assets/shell.js', name: 'AppShell', imports: ['index.html'], dynamicImports: ['src/pages/SettingsPage.tsx'] },
        'src/pages/SettingsPage.tsx': { file: 'assets/set.js', imports: ['_shell.js'] },
      }),
    )

    expect(publicAssetFiles(dist)).toEqual([
      'assets/e1.js',
      'assets/logo.svg',
      'assets/p1.js',
      'assets/s1.css',
      'assets/sh.js',
    ])
    expect(publicGateProblems(dist)).toEqual([])
  })

  it('reports a public page that lazy-loads a chunk anonymous visitors cannot download', () => {
    mkdirSync(join(dist, '.vite'))
    write(
      '.vite/manifest.json',
      JSON.stringify({
        'index.html': { file: 'assets/e1.js', dynamicImports: ['_shell.js', 'src/pages/PortalPage.tsx', '_qr.js'] },
        'src/pages/PortalPage.tsx': { file: 'assets/p1.js', imports: ['index.html'], dynamicImports: ['_chart.js'] },
        '_shell.js': { file: 'assets/shell.js', name: 'AppShell' },
        '_qr.js': { file: 'assets/qr.js' },
        '_chart.js': { file: 'assets/chart.js' },
      }),
    )

    expect(publicGateProblems(dist)).toEqual([
      'index.html lazy-loads _qr.js, which anonymous visitors cannot download',
      'src/pages/PortalPage.tsx lazy-loads _chart.js, which anonymous visitors cannot download',
    ])
  })

  it('reports a missing manifest or a missing public page', () => {
    expect(publicGateProblems(dist)).toEqual(['.vite/manifest.json is missing (build.manifest must stay enabled)'])

    mkdirSync(join(dist, '.vite'))
    write('.vite/manifest.json', JSON.stringify({ 'index.html': { file: 'assets/e1.js' } }))

    expect(publicGateProblems(dist)).toEqual(['src/pages/PortalPage.tsx is missing from .vite/manifest.json'])
  })
})
