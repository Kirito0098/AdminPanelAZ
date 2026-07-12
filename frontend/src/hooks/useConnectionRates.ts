import { useEffect, useRef, useState } from 'react'

type RateSample = { rx: number; tx: number; at: number }

export type ConnectionRate = {
  rxBps: number | null
  txBps: number | null
  /** True after first sample while waiting for a second tick (or after counter reset). */
  pending: boolean
}

/**
 * Compute per-row rx/tx bitrate between overview snapshots.
 * First tick → pending; negative delta (counter reset) → reset baseline.
 * Keeps last good rates if a tick has dt<=0 (duplicate timestamp).
 */
export function useConnectionRates(
  rows: Array<{ key: string; rx: number; tx: number }>,
  timestamp?: string | null,
): Map<string, ConnectionRate> {
  const prevRef = useRef<Map<string, RateSample>>(new Map())
  const lastGoodRef = useRef<Map<string, ConnectionRate>>(new Map())
  const rowsRef = useRef(rows)
  rowsRef.current = rows
  const [rates, setRates] = useState<Map<string, ConnectionRate>>(() => new Map())

  useEffect(() => {
    const currentRows = rowsRef.current
    const at = timestamp ? Date.parse(timestamp) : Date.now()
    const atMs = Number.isNaN(at) ? Date.now() : at
    const nextPrev = new Map<string, RateSample>()
    const nextRates = new Map<string, ConnectionRate>()
    const seen = new Set<string>()

    for (const row of currentRows) {
      seen.add(row.key)
      const samplePrev = prevRef.current.get(row.key)
      nextPrev.set(row.key, { rx: row.rx, tx: row.tx, at: atMs })
      if (!samplePrev) {
        nextRates.set(row.key, { rxBps: null, txBps: null, pending: true })
        continue
      }
      const dt = (atMs - samplePrev.at) / 1000
      if (dt <= 0) {
        const kept = lastGoodRef.current.get(row.key)
        nextRates.set(
          row.key,
          kept ?? { rxBps: null, txBps: null, pending: true },
        )
        // Keep previous baseline so the next real tick still has a valid prior.
        nextPrev.set(row.key, samplePrev)
        continue
      }
      const dRx = row.rx - samplePrev.rx
      const dTx = row.tx - samplePrev.tx
      if (dRx < 0 || dTx < 0) {
        nextRates.set(row.key, { rxBps: null, txBps: null, pending: true })
        lastGoodRef.current.delete(row.key)
        continue
      }
      const computed: ConnectionRate = {
        rxBps: (dRx * 8) / dt,
        txBps: (dTx * 8) / dt,
        pending: false,
      }
      nextRates.set(row.key, computed)
      lastGoodRef.current.set(row.key, computed)
    }

    for (const key of lastGoodRef.current.keys()) {
      if (!seen.has(key)) lastGoodRef.current.delete(key)
    }

    prevRef.current = nextPrev
    setRates(nextRates)
  }, [timestamp])

  return rates
}
