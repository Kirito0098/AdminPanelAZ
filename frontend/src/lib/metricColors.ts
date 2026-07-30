/** Threshold colors for resource usage bars (CPU / RAM / disk). */
export function metricBarClass(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return 'fill-muted-foreground/40'
  if (value >= 90) return 'fill-red-500'
  if (value >= 75) return 'fill-amber-500'
  return 'fill-emerald-500'
}

