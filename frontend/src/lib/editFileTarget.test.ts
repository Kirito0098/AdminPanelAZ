import { describe, expect, it } from 'vitest'

import { editorMatchesTarget, loadEditFile } from './editFileTarget'
import { createLatestRequest } from './latestRequest'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

describe('editorMatchesTarget', () => {
  it('allows saving the file and node whose content is in the editor', () => {
    expect(editorMatchesTarget({ key: 'include-hosts', nodeId: 1 }, 'include-hosts', 1)).toBe(true)
  })

  it('refuses saving under another file or node, or before any content loaded', () => {
    expect(editorMatchesTarget({ key: 'include-hosts', nodeId: 1 }, 'exclude-hosts', 1)).toBe(false)
    expect(editorMatchesTarget({ key: 'include-hosts', nodeId: 1 }, 'include-hosts', 2)).toBe(false)
    expect(editorMatchesTarget(null, 'include-hosts', 1)).toBe(false)
    expect(editorMatchesTarget({ key: 'include-hosts', nodeId: 1 }, null, 1)).toBe(false)
  })
})

describe('loadEditFile', () => {
  it('keeps the file opened last when the previous file answers later', async () => {
    const requests = createLatestRequest<number | null>(1)
    const answers: Record<string, ReturnType<typeof deferred<{ content: string }>>> = {
      a: deferred(),
      b: deferred(),
    }
    const applied: Array<{ key: string; nodeId: number | null; content: string }> = []
    const handlers = {
      apply: (loaded: { key: string; nodeId: number | null }, content: string) =>
        applied.push({ ...loaded, content }),
      fail: () => {},
    }

    const first = loadEditFile(requests, 'a', 1, (key) => answers[key].promise, handlers)
    const second = loadEditFile(requests, 'b', 1, (key) => answers[key].promise, handlers)
    answers.b.resolve({ content: 'B' })
    await second
    answers.a.resolve({ content: 'A' })
    await first

    expect(applied).toEqual([{ key: 'b', nodeId: 1, content: 'B' }])
  })

  it('drops the answer about the node shown before', async () => {
    const requests = createLatestRequest<number | null>(1)
    const answer = deferred<{ content: string }>()
    const applied: string[] = []

    const pending = loadEditFile(requests, 'a', 1, () => answer.promise, {
      apply: (_loaded, content) => applied.push(content),
      fail: () => {},
    })
    requests.reset(2)
    answer.resolve({ content: 'node 1' })
    await pending

    expect(applied).toEqual([])
  })
})
