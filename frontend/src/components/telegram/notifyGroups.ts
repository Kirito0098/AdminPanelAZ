export function enabledCount(keys: string[], toggles: Record<string, boolean>): number {
  return keys.filter((key) => toggles[key] === true).length
}

export function isIndeterminate(keys: string[], toggles: Record<string, boolean>): boolean {
  if (keys.length === 0) return false
  const count = enabledCount(keys, toggles)
  return count > 0 && count < keys.length
}

export function applyGroupToggle(
  toggles: Record<string, boolean>,
  keys: string[],
  enabled: boolean,
): Record<string, boolean> {
  const next = { ...toggles }
  for (const key of keys) next[key] = enabled
  return next
}
