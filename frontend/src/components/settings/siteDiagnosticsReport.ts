import type { SiteDiagnosticsCheck, SiteDiagnosticsReport, SiteDiagnosticsStatus } from '@/types'

const SUMMARY_TITLES: Record<SiteDiagnosticsStatus, string> = {
  fail: 'Диагностика завершена с ошибками',
  warn: 'Диагностика завершена с предупреждениями',
  ok: 'Диагностика: критических проблем не найдено',
}

function worstStatus(checks: SiteDiagnosticsCheck[]): SiteDiagnosticsStatus {
  if (checks.some((check) => check.status === 'fail')) return 'fail'
  if (checks.some((check) => check.status === 'warn')) return 'warn'
  return 'ok'
}

function countStatus(checks: SiteDiagnosticsCheck[], status: SiteDiagnosticsStatus) {
  return checks.filter((check) => check.status === status).length
}

/**
 * Replaces the check with the same id and recounts step statuses, the «Итог» check and the summary
 * the same way the backend builds them after a full run.
 */
export function replaceDiagnosticsCheck(
  report: SiteDiagnosticsReport,
  next: SiteDiagnosticsCheck,
): SiteDiagnosticsReport {
  if (!next.id) return report
  const body = report.results
    .filter((check) => check.category !== 'summary')
    .map((check) => (check.id === next.id ? next : check))
  const bodyCounts = `ok=${countStatus(body, 'ok')}, warn=${countStatus(body, 'warn')}, fail=${countStatus(body, 'fail')}`
  const overall = worstStatus(body)
  const fix = (check: SiteDiagnosticsCheck): SiteDiagnosticsCheck => {
    if (check.id === next.id) return next
    if (check.category === 'summary') {
      return { ...check, status: overall, title: SUMMARY_TITLES[overall], detail: bodyCounts }
    }
    return check
  }
  const results = report.results.map(fix)
  const steps = report.steps.map((step) => {
    const checks = step.checks.map(fix)
    return { ...step, checks, status: worstStatus(checks) }
  })
  const fail = countStatus(results, 'fail')
  return {
    ...report,
    steps,
    results,
    success: fail === 0,
    summary: { ok: countStatus(results, 'ok'), warn: countStatus(results, 'warn'), fail, has_failures: fail > 0 },
  }
}
