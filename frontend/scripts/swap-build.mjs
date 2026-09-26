#!/usr/bin/env node
// Puts a finished build in place of the served one with two renames, so the running panel
// never sees a half-emptied directory (vite empties outDir before writing index.html).
import { existsSync, renameSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

export function swapBuildDir(next, target) {
  if (!existsSync(join(next, 'index.html'))) {
    throw new Error(`${next}/index.html is missing: build incomplete, ${target} left as is`)
  }
  const old = `${target}.old`
  rmSync(old, { recursive: true, force: true })
  const hadTarget = existsSync(target)
  if (hadTarget) renameSync(target, old)
  try {
    renameSync(next, target)
  } catch (err) {
    if (hadTarget) renameSync(old, target)
    throw err
  }
  rmSync(old, { recursive: true, force: true })
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const [next, target] = process.argv.slice(2)
  if (!next || !target) {
    console.error('usage: swap-build.mjs <new-build-dir> <served-dir>')
    process.exit(2)
  }
  try {
    swapBuildDir(next, target)
  } catch (err) {
    console.error(err instanceof Error ? err.message : err)
    process.exit(1)
  }
}
