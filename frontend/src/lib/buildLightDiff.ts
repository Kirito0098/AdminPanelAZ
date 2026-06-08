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

function buildMyersDiff(baseLines: string[], currentLines: string[]): DiffOp[] {
  const n = baseLines.length
  const m = currentLines.length
  const max = n + m
  const v = new Map<number, number>()
  const trace: Map<number, number>[] = []
  v.set(1, 0)

  for (let d = 0; d <= max; d += 1) {
    trace.push(new Map(v))
    for (let k = -d; k <= d; k += 2) {
      const xFromKMinus = v.get(k - 1)
      const xFromKPlus = v.get(k + 1)

      let x: number
      if (k === -d || (k !== d && (xFromKMinus ?? -Infinity) < (xFromKPlus ?? -Infinity))) {
        x = xFromKPlus ?? 0
      } else {
        x = (xFromKMinus ?? 0) + 1
      }

      let y = x - k
      while (x < n && y < m && baseLines[x] === currentLines[y]) {
        x += 1
        y += 1
      }

      v.set(k, x)

      if (x >= n && y >= m) {
        const ops: DiffOp[] = []
        let backX = n
        let backY = m

        for (let backD = trace.length - 1; backD > 0; backD -= 1) {
          const prevV = trace[backD - 1]
          const backK = backX - backY
          let prevK: number

          if (
            backK === -backD ||
            (backK !== backD &&
              (prevV.get(backK - 1) ?? -Infinity) < (prevV.get(backK + 1) ?? -Infinity))
          ) {
            prevK = backK + 1
          } else {
            prevK = backK - 1
          }

          const prevX = prevV.get(prevK) ?? 0
          const prevY = prevX - prevK

          while (backX > prevX && backY > prevY) {
            backX -= 1
            backY -= 1
          }

          if (backX === prevX && backY > prevY) {
            backY -= 1
            ops.push({ type: 'add', lineNumber: backY + 1, text: currentLines[backY] })
          } else if (backX > prevX && backY === prevY) {
            backX -= 1
            ops.push({ type: 'remove', lineNumber: backX + 1, text: baseLines[backX] })
          }
        }

        while (backX > 0) {
          backX -= 1
          ops.push({ type: 'remove', lineNumber: backX + 1, text: baseLines[backX] })
        }
        while (backY > 0) {
          backY -= 1
          ops.push({ type: 'add', lineNumber: backY + 1, text: currentLines[backY] })
        }

        ops.reverse()
        return ops
      }
    }
  }

  return buildIndexedDiff(baseLines, currentLines)
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

export function formatDiffSummary(counts: DiffCounts): string {
  if (!counts.added && !counts.removed) {
    return 'Нет отличий от сохранённой версии'
  }
  return `Добавлено: ${counts.added}, удалено: ${counts.removed}`
}
