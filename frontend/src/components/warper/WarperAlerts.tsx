import { Link } from 'react-router-dom'
import SettingsAlert from '@/components/settings/SettingsAlert'
import type { Node, WarperHealthResponse } from '@/types'
import { INSTALL_CMD, formatNodeLabel } from './utils'

interface WarperAlertsProps {
  health: WarperHealthResponse | null
  activeNode: Node | null
  loadError: string | null
}

function formatMissingComponents(health: WarperHealthResponse | null): string | null {
  const missing = health?.missing_components ?? []
  if (missing.length === 0) return null
  const labels: Record<string, string> = {
    warper_api: 'Python API',
    warper_bin: 'CLI warper',
    warper_symlink: 'симлинк /usr/local/bin/warper',
    warper_bin_broken_symlink: 'битый симлинк warper',
  }
  return missing.map((key) => labels[key] ?? key).join(', ')
}

export default function WarperAlerts({ health, activeNode, loadError }: WarperAlertsProps) {
  const nodeLabel = formatNodeLabel(health, activeNode)
  const missingDetail = formatMissingComponents(health)

  return (
    <>
      {loadError && (
        <SettingsAlert variant="danger" title="Не удалось связаться с AZ-WARP">
          {loadError}
        </SettingsAlert>
      )}

      {health && !health.installed && (
        <SettingsAlert variant="warning" title="AZ-WARP не установлен на проверяемом узле">
          Панель управляет только <strong>активным узлом</strong>: {nodeLabel}. Если установка уже
          выполнена на другом сервере — переключите узел в селекторе в шапке.
          {missingDetail && (
            <>
              {' '}
              Не найдено: <strong>{missingDetail}</strong>.
            </>
          )}
          <pre className="mt-2 overflow-x-auto rounded bg-muted p-2 font-mono text-xs">{INSTALL_CMD}</pre>
        </SettingsAlert>
      )}

      {health?.conflict_antizapret_warp && (
        <SettingsAlert variant="danger" title="Конфликт Cloudflare WARP">
          <strong>ANTIZAPRET_WARP=y</strong> блокирует доменную маршрутизацию AZ-WARP. Отключите
          встроенный WARP в{' '}
          <Link to="/antizapret" className="font-medium text-primary underline-offset-4 hover:underline">
            Конфиг AntiZapret
          </Link>
          .
        </SettingsAlert>
      )}
    </>
  )
}
