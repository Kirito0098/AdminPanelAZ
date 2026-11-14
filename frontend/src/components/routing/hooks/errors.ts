export function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error) return err.message
  return fallback
}
