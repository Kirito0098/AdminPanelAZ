import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { eagerChartChunks, eagerChunks, pagesWithChartCode } from '../../scripts/check-entry-chunks.mjs'

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
    write('assets/charts-Ab_1.js', 'recharts-surface')
    write('assets/TrafficPage-Xy-9.js', 'import{C}from"./charts-Ab_1.js"')
    write('assets/WarperPage-Qw12.js', 'const C=()=>import("./charts-Ab_1.js")')
    write('assets/MonitoringPage-Zz12.js', 'import{C}from"./charts-Ab_1.js"')
    write('assets/ServerMonitorPage-Zz12.js', 'import{C}from"./charts-Ab_1.js"')
    write('assets/SettingsPage-Aa12.js', 'import"./shared-Bb12.js"')
    write('assets/shared-Bb12.js', 'import"./charts-Ab_1.js"')
    write('assets/pageHelpers-Cc12.js', 'import"./charts-Ab_1.js"')

    expect(pagesWithChartCode(dist)).toEqual(['SettingsPage', 'TrafficPage'])
  })
})
