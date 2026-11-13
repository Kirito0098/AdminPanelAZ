import type { CidrDbStatus, CidrProviderInfo } from '@/types'
import { STAGE_BUILD, STAGE_DEPLOY, STAGE_LOAD } from './routingLabels'
import { pluralProviders, type PipelineStage } from './utils'

export type RoutingTab = 'overview' | 'providers' | 'pipeline' | 'analysis' | 'settings'

type WorkflowStage = 1 | 2 | 3 | 4

export interface PipelineStageMeta {
  stage: PipelineStage
  /** Якорь блока этапа на вкладке обновления списков. */
  id: string
  /** Полное название этапа: «Загрузка данных на контроллер». */
  label: string
  /** Одно слово для навигации и бейджей: «Загрузка». */
  shortLabel: string
  /** Компактная формулировка шага для цепочки этапов и подсказок. */
  description: string
}

/** Единственный источник описания этапов пайплайна (навигация, заголовки, цепочка). */
export const PIPELINE_STAGES: readonly PipelineStageMeta[] = [
  {
    stage: 1,
    id: 'pipeline-stage-1',
    label: `${STAGE_LOAD} данных на контроллер`,
    shortLabel: STAGE_LOAD,
    description: 'Данные на контроллер (SQLite)',
  },
  {
    stage: 2,
    id: 'pipeline-stage-2',
    label: `${STAGE_BUILD} списков на контроллере`,
    shortLabel: STAGE_BUILD,
    description: 'Списки на контроллере',
  },
  {
    stage: 3,
    id: 'pipeline-stage-3',
    label: `${STAGE_DEPLOY} списков на узел`,
    shortLabel: STAGE_DEPLOY,
    description: 'Списки на узел',
  },
]

export function getPipelineStageMeta(stage: PipelineStage): PipelineStageMeta {
  return PIPELINE_STAGES.find((item) => item.stage === stage) ?? PIPELINE_STAGES[0]
}

export interface WorkflowStep {
  stage: WorkflowStage
  label: string
  shortLabel: string
  tab: RoutingTab
  anchor?: string
  status: 'done' | 'current' | 'pending' | 'warning'
  summary: string
}

export interface RoutingWorkflowState {
  steps: WorkflowStep[]
  currentStage: WorkflowStage | null
  nextAction: {
    label: string
    tab: RoutingTab
    anchor?: string
    hint: string
  } | null
  enabledCount: number
  totalProviders: number
  onNodeCount: number
  pendingCompileCount: number
  pendingDeployCount: number
  pendingCompileNames: string[]
  compileRecentlyCompleted: boolean
  optionalCompileRemaining: boolean
  hasAlerts: boolean
}

export function hasControllerArtifact(cidrDb: CidrDbStatus | null, filename: string): boolean {
  const artifact = cidrDb?.compile_artifacts?.[filename]
  return Boolean(artifact?.exists)
}

function hasDbData(cidrDb: CidrDbStatus | null, filename: string): boolean {
  const dbMeta = cidrDb?.providers?.[filename]
  return (
    (dbMeta?.cidr_count ?? 0) > 0 &&
    (dbMeta?.refresh_status === 'ok' || dbMeta?.refresh_status === 'partial')
  )
}

export function providerNeedsCompile(cidrDb: CidrDbStatus | null, provider: CidrProviderInfo): boolean {
  return hasDbData(cidrDb, provider.filename) && !hasControllerArtifact(cidrDb, provider.filename)
}

export function providerNeedsDeploy(cidrDb: CidrDbStatus | null, provider: CidrProviderInfo): boolean {
  return (
    hasDbData(cidrDb, provider.filename) &&
    hasControllerArtifact(cidrDb, provider.filename) &&
    !provider.has_source
  )
}

function ingestSummary(cidrDb: CidrDbStatus | null): string {
  const total = cidrDb?.total_cidrs ?? 0
  const status = cidrDb?.last_refresh_status
  if (total === 0) return 'Нет данных в SQLite'
  if (status === 'error') return 'Ошибка последнего ingest'
  if (status === 'partial') return `${total.toLocaleString('ru-RU')} CIDR · частично`
  return `${total.toLocaleString('ru-RU')} CIDR в SQLite`
}

function compileSummary(
  cidrDb: CidrDbStatus | null,
  pendingCount: number,
  compileRecentlyCompleted: boolean,
  pendingDeployCount: number,
  pendingNames: string[],
): string {
  const compile = cidrDb?.last_compile_at
  if (pendingCount > 0) {
    if (compileRecentlyCompleted && pendingDeployCount > 0) {
      const tail =
        pendingNames.length === 1
          ? `«${pendingNames[0]}» без файла — можно пропустить`
          : `${pluralProviders(pendingCount)} без файла — необязательно`
      return `Сборка завершена · ${tail}`
    }
    if (pendingNames.length === 1) {
      return `«${pendingNames[0]}» ждёт сборки`
    }
    return `${pluralProviders(pendingCount)} ждут сборки`
  }
  if (!compile?.finished_at) return 'Списки ещё не собирались'
  if (compile.status !== 'completed') return 'Последняя сборка не завершена'
  return `${compile.files_updated ?? 0} файлов на контроллере`
}

function deploySummary(
  cidrDb: CidrDbStatus | null,
  pendingCount: number,
  onNodeCount: number,
): string {
  if (pendingCount > 0) return `${pluralProviders(pendingCount)} ждут ${STAGE_DEPLOY.toLowerCase()}`
  const deploy = cidrDb?.last_deploy
  if (!deploy?.finished_at) return `${STAGE_DEPLOY} ещё не выполнялось`
  if (deploy.status !== 'completed' && deploy.status !== 'ok') return `Последнее ${STAGE_DEPLOY.toLowerCase()} с ошибками`
  return `${pluralProviders(onNodeCount)} на узле`
}

function providersSummary(enabledCount: number, onNodeCount: number): string {
  if (onNodeCount === 0) return `Сначала выполните ${STAGE_DEPLOY.toLowerCase()}`
  if (enabledCount === 0) return 'Ни один провайдер не включён'
  return `${enabledCount} из ${onNodeCount} включено для маршрутизации`
}

export function getRoutingWorkflowState(
  providers: CidrProviderInfo[],
  cidrDb: CidrDbStatus | null,
): RoutingWorkflowState {
  const enabledCount = providers.filter((p) => p.enabled).length
  const onNodeCount = providers.filter((p) => p.has_source).length
  const pendingCompileProviders = providers.filter((p) => providerNeedsCompile(cidrDb, p))
  const pendingCompileCount = pendingCompileProviders.length
  const pendingCompileNames = pendingCompileProviders.map((p) => p.name)
  const pendingDeployCount = providers.filter((p) => providerNeedsDeploy(cidrDb, p)).length
  const hasAlerts = (cidrDb?.alerts?.length ?? 0) > 0
  const hasDb = (cidrDb?.total_cidrs ?? 0) > 0
  const refreshOk =
    cidrDb?.last_refresh_status === 'ok' || cidrDb?.last_refresh_status === 'partial'
  const compileRecentlyCompleted = cidrDb?.last_compile_at?.status === 'completed'
  const hasCompiledArtifacts = Object.values(cidrDb?.compile_artifacts ?? {}).some((a) => a.exists)
  const shouldPrioritizeDeploy =
    pendingDeployCount > 0 && (compileRecentlyCompleted || hasCompiledArtifacts)

  const optionalCompileRemaining = compileRecentlyCompleted && pendingCompileCount > 0

  let currentStage: WorkflowStage | null = null

  if (!hasDb || !refreshOk) {
    currentStage = 1
  } else if (shouldPrioritizeDeploy) {
    currentStage = 3
  } else if (pendingCompileCount > 0) {
    currentStage = 2
  } else if (pendingDeployCount > 0) {
    currentStage = 3
  } else if (onNodeCount > 0 && enabledCount === 0) {
    currentStage = 4
  } else {
    currentStage = null
  }

  if (hasAlerts && currentStage == null) {
    currentStage = 1
  }

  const stageStatus = (stage: WorkflowStage): WorkflowStep['status'] => {
    if (currentStage == null) return 'done'

    if (stage === 2 && optionalCompileRemaining && currentStage >= 3) {
      return 'warning'
    }

    if (stage < currentStage) return 'done'
    if (stage === currentStage) return hasAlerts && stage === 1 ? 'warning' : 'current'
    return 'pending'
  }

  const [loadStage, buildStage, deployStage] = PIPELINE_STAGES

  const steps: WorkflowStep[] = [
    {
      stage: 1,
      label: loadStage.label,
      shortLabel: loadStage.shortLabel,
      tab: 'pipeline',
      anchor: loadStage.id,
      status: stageStatus(1),
      summary: ingestSummary(cidrDb),
    },
    {
      stage: 2,
      label: buildStage.label,
      shortLabel: buildStage.shortLabel,
      tab: 'pipeline',
      anchor: buildStage.id,
      status: stageStatus(2),
      summary: compileSummary(
        cidrDb,
        pendingCompileCount,
        compileRecentlyCompleted,
        pendingDeployCount,
        pendingCompileNames,
      ),
    },
    {
      stage: 3,
      label: deployStage.label,
      shortLabel: deployStage.shortLabel,
      tab: 'pipeline',
      anchor: deployStage.id,
      status: stageStatus(3),
      summary: deploySummary(cidrDb, pendingDeployCount, onNodeCount),
    },
    {
      stage: 4,
      label: 'Включить провайдеров',
      shortLabel: 'Маршруты',
      tab: 'providers',
      status: stageStatus(4),
      summary: providersSummary(enabledCount, onNodeCount),
    },
  ]

  let nextAction: RoutingWorkflowState['nextAction'] = null

  if (currentStage === 1) {
    nextAction = {
      label: 'Обновить из интернета',
      tab: 'pipeline',
      anchor: loadStage.id,
      hint: 'Загрузите CIDR-провайдеров в SQLite на контроллере (этап 1).',
    }
  } else if (currentStage === 2) {
    nextAction = {
      label: 'Собрать списки',
      tab: 'pipeline',
      anchor: buildStage.id,
      hint:
        pendingCompileNames.length === 1
          ? `Сформируйте файл для «${pendingCompileNames[0]}» из локальной БД (этап 2).`
          : 'Сформируйте AP-*-include-ips.txt из локальной БД (этап 2).',
    }
  } else if (currentStage === 3) {
    nextAction = {
      label: 'Развернуть на узел',
      tab: 'pipeline',
      anchor: deployStage.id,
      hint: optionalCompileRemaining
        ? 'Списки собраны. Отправьте их на узел — провайдеры без файла можно пропустить.'
        : 'Отправьте готовые списки с контроллера на узел AntiZapret.',
    }
  } else if (currentStage === 4) {
    nextAction = {
      label: 'Выбрать провайдеров',
      tab: 'providers',
      hint: 'Включите нужные списки, затем на вкладке «Провайдеры» выполните doall + client.sh 7.',
    }
  }

  return {
    steps,
    currentStage,
    nextAction,
    enabledCount,
    totalProviders: providers.length,
    onNodeCount,
    pendingCompileCount,
    pendingDeployCount,
    pendingCompileNames,
    compileRecentlyCompleted,
    optionalCompileRemaining,
    hasAlerts,
  }
}
