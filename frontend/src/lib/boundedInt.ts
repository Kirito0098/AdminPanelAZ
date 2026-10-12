/** Parse a non-negative integer from user input; null if malformed or outside [min, max]. */
export function parseBoundedInt(raw: string, min: number, max: number): number | null {
  const trimmed = raw.trim()
  if (!/^\d+$/.test(trimmed)) return null
  const value = Number.parseInt(trimmed, 10)
  return value >= min && value <= max ? value : null
}
