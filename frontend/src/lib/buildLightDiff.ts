/** Line diff utilities (ported from AdminAntizapret edit_files/diff.js). */

export type DiffOp = {
  type: 'add' | 'remove'
  lineNumber: number
  text: string
}

export type DiffMode = 'myers' | 'indexed'

export type DiffResult = {
  mode: DiffMode
  ops: DiffOp[]
}

export type DiffCounts = {
  added: number
  removed: number
}

function splitLines(value: string): string[] {
  if (!value) {
    return []
  }
  return value.split(/\r?\n/)
}

function buildIndexedDiff(baseLines: string[], currentLines: string[]): DiffOp[] {
  const ops: DiffOp[] = []
  const maxLen = Math.max(baseLines.length, currentLines.length)

  for (let i = 0; i < maxLen; i += 1) {
    const baseLine = baseLines[i]
    const currentLine = currentLines[i]

    if (baseLine === currentLine) {
      continue
    }

    if (typeof baseLine !== 'undefined') {
      ops.push({ type: 'remove', lineNumber: i + 1, text: baseLine })
    }
    if (typeof currentLine !== 'undefined') {
      ops.push({ type: 'add', lineNumber: i + 1, text: currentLine })
    }
  }

  return ops
}

/**
 * Myers shortest-edit-script diff with correct backtracking
 * (jcoglan / Myers 1986). The previous Map-based port mishandled
 * reconstruction and produced empty "L0" ops for common cases like
 * replacing a trailing-newline-only file with real content.
 */
function buildMyersDiff(baseLines: string[], currentLines: string[]): DiffOp[] {
  const n = baseLines.length
  const m = currentLines.length

  if (n === 0) {
    return currentLines.map((text, i) => ({
      type: 'add' as const,
      lineNumber: i + 1,
      text,
    }))
  }
  if (m === 0) {
    return baseLines.map((text, i) => ({
      type: 'remove' as const,
      lineNumber: i + 1,
      text,
    }))
  }

  const max = n + m
  const offset = max
  const v = new Array<number>(2 * max + 1).fill(0)
  const trace: number[][] = []

  outer: for (let d = 0; d <= max; d += 1) {
    for (let k = -d; k <= d; k += 2) {
      let x: number
      if (k === -d || (k !== d && v[k - 1 + offset] < v[k + 1 + offset])) {
        x = v[k + 1 + offset]
      } else {
        x = v[k - 1 + offset] + 1
      }

      let y = x - k
      while (x < n && y < m && baseLines[x] === currentLines[y]) {
        x += 1
        y += 1
      }

      v[k + offset] = x

      if (x >= n && y >= m) {
        trace.push(v.slice())
        break outer
      }
    }
    trace.push(v.slice())
  }

  const ops: DiffOp[] = []
  let x = n
  let y = m

  for (let d = trace.length - 1; d > 0; d -= 1) {
    const vSnap = trace[d]
    const k = x - y

    let prevK: number
    if (k === -d || (k !== d && vSnap[k - 1 + offset] < vSnap[k + 1 + offset])) {
      prevK = k + 1
    } else {
      prevK = k - 1
    }

    const prevX = vSnap[prevK + offset]
    const prevY = prevX - prevK

    while (x > prevX && y > prevY) {
      x -= 1
      y -= 1
    }

    if (x === prevX) {
      ops.push({
        type: 'add',
        lineNumber: prevY + 1,
        text: currentLines[prevY],
      })
    } else {
      ops.push({
        type: 'remove',
        lineNumber: prevX + 1,
        text: baseLines[prevX],
      })
    }

    x = prevX
    y = prevY
  }

  ops.reverse()
  return ops
}

export function buildLightDiff(baseValue: string, currentValue: string): DiffResult {
  const baseLines = splitLines(baseValue)
  const currentLines = splitLines(currentValue)

  const complexity = baseLines.length * currentLines.length
  if (complexity > 220000) {
    return {
      mode: 'indexed',
      ops: buildIndexedDiff(baseLines, currentLines),
    }
  }

  return {
    mode: 'myers',
    ops: buildMyersDiff(baseLines, currentLines),
  }
}

export function countDiffOps(ops: DiffOp[]): DiffCounts {
  let added = 0
  let removed = 0
  for (const op of ops) {
    if (op.type === 'add') added += 1
    else removed += 1
  }
  return { added, removed }
}
