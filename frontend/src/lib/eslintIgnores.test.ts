import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { ESLint } from 'eslint'
import { describe, expect, it } from 'vitest'

const frontendDir = fileURLToPath(new URL('../..', import.meta.url))

describe('eslint.config.js', () => {
  it.each(['dist', 'dist.next', 'dist.old'])('ignores build output in %s', async (dir) => {
    const eslint = new ESLint({ cwd: frontendDir })
    expect(await eslint.isPathIgnored(join(frontendDir, dir, 'assets', 'index.js'))).toBe(true)
  })

  it('still lints sources', async () => {
    const eslint = new ESLint({ cwd: frontendDir })
    expect(await eslint.isPathIgnored(join(frontendDir, 'src', 'main.tsx'))).toBe(false)
  })
})
