import { spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { swapBuildDir } from '../../scripts/swap-build.mjs'

let root: string

function build(dir: string, marker: string) {
  mkdirSync(join(dir, 'assets'), { recursive: true })
  writeFileSync(join(dir, 'index.html'), marker)
  writeFileSync(join(dir, 'assets', `${marker}.js`), marker)
}

describe('swapBuildDir', () => {
  beforeEach(() => {
    root = mkdtempSync(join(tmpdir(), 'swap-build-'))
  })

  afterEach(() => {
    rmSync(root, { recursive: true, force: true })
  })

  it('replaces the served build and leaves no leftovers', () => {
    build(join(root, 'dist'), 'old')
    build(join(root, 'dist.next'), 'new')

    swapBuildDir(join(root, 'dist.next'), join(root, 'dist'))

    expect(readFileSync(join(root, 'dist', 'index.html'), 'utf8')).toBe('new')
    expect(existsSync(join(root, 'dist', 'assets', 'old.js'))).toBe(false)
    expect(existsSync(join(root, 'dist.next'))).toBe(false)
    expect(existsSync(join(root, 'dist.old'))).toBe(false)
  })

  it('works for the first build and clears a leftover from an interrupted swap', () => {
    build(join(root, 'dist.old'), 'stale')
    build(join(root, 'dist.next'), 'new')

    swapBuildDir(join(root, 'dist.next'), join(root, 'dist'))

    expect(readFileSync(join(root, 'dist', 'index.html'), 'utf8')).toBe('new')
    expect(existsSync(join(root, 'dist.old'))).toBe(false)
  })

  it('swaps over a leftover from an interrupted swap', () => {
    build(join(root, 'dist'), 'old')
    build(join(root, 'dist.old'), 'stale')
    build(join(root, 'dist.next'), 'new')

    swapBuildDir(join(root, 'dist.next'), join(root, 'dist'))

    expect(readFileSync(join(root, 'dist', 'index.html'), 'utf8')).toBe('new')
    expect(existsSync(join(root, 'dist.old'))).toBe(false)
  })

  it('keeps serving the old build when the new one has no index.html', () => {
    build(join(root, 'dist'), 'old')
    mkdirSync(join(root, 'dist.next', 'assets'), { recursive: true })

    expect(() => swapBuildDir(join(root, 'dist.next'), join(root, 'dist'))).toThrow(/index\.html/)

    expect(readFileSync(join(root, 'dist', 'index.html'), 'utf8')).toBe('old')
    expect(existsSync(join(root, 'dist.old'))).toBe(false)
  })

  it('puts the old build back when the new one cannot be moved in', async () => {
    const dist = join(root, 'dist')
    const next = join(root, 'dist.next')
    build(dist, 'old')
    build(next, 'new')
    vi.resetModules()
    vi.doMock('node:fs', async (importOriginal) => {
      const actual = await importOriginal<typeof import('node:fs')>()
      return {
        ...actual,
        renameSync: (from: string, to: string) => {
          if (from === next) throw new Error('EXDEV')
          actual.renameSync(from, to)
        },
      }
    })
    try {
      const { swapBuildDir: swap } = await import('../../scripts/swap-build.mjs')
      expect(() => swap(next, dist)).toThrow('EXDEV')
    } finally {
      vi.doUnmock('node:fs')
    }

    expect(readFileSync(join(dist, 'index.html'), 'utf8')).toBe('old')
    expect(existsSync(join(root, 'dist.old'))).toBe(false)
    expect(existsSync(join(next, 'index.html'))).toBe(true)
  })
})

describe('swap-build.mjs command line', () => {
  const frontendDir = fileURLToPath(new URL('../..', import.meta.url))
  const run = (...args: string[]) =>
    spawnSync(process.execPath, ['scripts/swap-build.mjs', ...args], { cwd: frontendDir, encoding: 'utf8' })

  beforeEach(() => {
    root = mkdtempSync(join(tmpdir(), 'swap-build-cli-'))
  })

  afterEach(() => {
    rmSync(root, { recursive: true, force: true })
  })

  it('swaps the directories when run the way package.json runs it', () => {
    build(join(root, 'dist'), 'old')
    build(join(root, 'dist.next'), 'new')

    const result = run(join(root, 'dist.next'), join(root, 'dist'))

    expect(result.status).toBe(0)
    expect(readFileSync(join(root, 'dist', 'index.html'), 'utf8')).toBe('new')
  })

  it('fails the build when the new directory is incomplete', () => {
    build(join(root, 'dist'), 'old')
    mkdirSync(join(root, 'dist.next'))

    const result = run(join(root, 'dist.next'), join(root, 'dist'))

    expect(result.status).toBe(1)
    expect(result.stderr).toContain('index.html is missing')
    expect(readFileSync(join(root, 'dist', 'index.html'), 'utf8')).toBe('old')
  })

  it('refuses to run without both directories', () => {
    expect(run(join(root, 'dist.next')).status).toBe(2)
  })
})

describe('build scripts', () => {
  const packageJson = JSON.parse(readFileSync(new URL('../../package.json', import.meta.url), 'utf8'))
  const scripts = packageJson.scripts as Record<string, string>

  it('build the panel next to the served dist and swap it in', () => {
    expect(scripts.build).toContain('--outDir dist.next')
    expect(scripts.build).toMatch(/&& node scripts\/swap-build\.mjs dist\.next dist$/)
  })

  it('finish the Mini App page inside the new build before swapping it in', () => {
    const steps = scripts['build:tg-mini'].split(' && ')
    const swap = steps.findIndex((s) => s.startsWith('node scripts/swap-build.mjs'))
    expect(steps[0]).toContain('--outDir ../backend/app/static/tg_mini.next')
    expect(swap).toBe(steps.length - 1)
    expect(steps[swap]).toBe('node scripts/swap-build.mjs ../backend/app/static/tg_mini.next ../backend/app/static/tg_mini')
    for (const step of steps.slice(1, swap)) {
      expect(step).toContain('tg_mini.next/')
      expect(step).not.toMatch(/static\/tg_mini\//)
    }
  })
})
