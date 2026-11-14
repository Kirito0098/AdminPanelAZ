import type { NginxImpact, ServerConfigPreview, ServerConfigStep } from '@/types'

export const NGINX_STEP_KEY = 'nginx'

/** Панель подключена snippet'ом внутрь чужого vhost (обычно StatusOpenVPN). */
export function isSnippetIntegration(impact?: NginxImpact | null): boolean {
  if (!impact) return false
  return (
    impact.integration_mode === 'subpath_snippet' ||
    (impact.panel_snippet_includes?.length ?? 0) > 0
  )
}

/** Обновление nginx может затронуть чужие блоки или vhost, в котором живёт панель. */
export function hasNginxRisk(impact?: NginxImpact | null): boolean {
  if (!impact) return false
  return (impact.foreign_locations?.length ?? 0) > 0 || isSnippetIntegration(impact)
}

/** По умолчанию отмечаем всё доступное, но nginx — только когда он ничего не ломает. */
export function defaultStepSelection(preview: ServerConfigPreview | null): string[] {
  if (!preview) return []
  return (preview.steps ?? [])
    .filter((step) => step.available)
    .filter((step) => !(step.key === NGINX_STEP_KEY && hasNginxRisk(preview.nginx_impact)))
    .map((step) => step.key)
}

/** Убираем из выбора шаги, которых больше нет в плане или которые недоступны. */
export function sanitizeStepSelection(
  selection: readonly string[],
  steps: readonly ServerConfigStep[],
): string[] {
  const available = new Set<string>(steps.filter((step) => step.available).map((step) => step.key))
  return selection.filter((key) => available.has(key))
}

/** Человекочитаемые причины, по которым обновление nginx рискованно. */
export function nginxRiskNotes(impact?: NginxImpact | null): string[] {
  if (!impact) return []
  const notes: string[] = []
  if (isSnippetIntegration(impact)) {
    notes.push(
      'Панель работает через snippet в vhost StatusOpenVPN/чужом vhost — обновление nginx может перезаписать этот vhost.',
    )
  }
  const foreign = impact.foreign_locations ?? []
  if (foreign.length) {
    const paths = foreign.map((item) => `${item.path} (${item.project})`).join(', ')
    notes.push(`В vhost панели есть ${paths} — обновление nginx может его удалить.`)
  }
  return notes
}
