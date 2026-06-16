import ConfirmDialog from '@/components/shared/ConfirmDialog'
import type { ConfirmAction } from './useRoutingPage'
import type { CidrDeployPreview } from '@/types'

const confirmMeta: Record<
  Exclude<ConfirmAction, null>,
  { title: string; description: string; confirmLabel: string; destructive?: boolean; alertTitle?: string }
> = {
  'apply-doall': {
    title: 'Применить маршрутизацию?',
    description:
      'Будет выполнен doall.sh на активном узле. Это может занять несколько минут и перезагрузить правила маршрутизации.',
    confirmLabel: 'Выполнить doall.sh',
    destructive: true,
    alertTitle: 'Длительная операция',
  },
  'sync-providers': {
    title: 'Синхронизировать провайдеров?',
    description: 'Файлы CIDR будут синхронизированы с конфигурацией AntiZapret на узле.',
    confirmLabel: 'Синхронизировать',
  },
  'generate-only': {
    title: 'Собрать CIDR-файлы из БД?',
    description:
      'Списки AP-*-include-ips.txt будут сгенерированы на контроллере из локальной SQLite БД. Файлы на узел не отправляются.',
    confirmLabel: 'Сгенерировать',
  },
  'deploy-only': {
    title: 'Развернуть CIDR на узлы?',
    description:
      'Ранее собранные файлы с контроллера будут отправлены на выбранные online-узлы (или все online) и синхронизированы с AntiZapret. Offline-узлы будут пропущены.',
    confirmLabel: 'Развернуть',
  },
  'generate-doall': {
    title: 'Полный цикл: сборка, deploy и doall?',
    description:
      'CIDR-файлы будут собраны из БД, развёрнуты на узел и применены через doall.sh. Операция длительная.',
    confirmLabel: 'Сгенерировать + doall',
    destructive: true,
    alertTitle: 'Длительная операция',
  },
  'rollback-cidr': {
    title: 'Откатить CIDR из runtime_backups?',
    description:
      'Файлы на контроллере будут восстановлены из выбранной резервной копии и развёрнуты на выбранные узлы. Операция в фоне.',
    confirmLabel: 'Откатить и развернуть',
    destructive: true,
    alertTitle: 'Откат deploy',
  },
}

interface ConfirmActionDialogProps {
  action: ConfirmAction
  onClose: () => void
  onConfirm: () => void
  loading?: boolean
  deployPreview?: CidrDeployPreview | null
  rollbackStamp?: string | null
}

export default function ConfirmActionDialog({
  action,
  onClose,
  onConfirm,
  loading,
  deployPreview,
  rollbackStamp,
}: ConfirmActionDialogProps) {
  if (!action) return null
  const meta = confirmMeta[action]

  const description =
    action === 'deploy-only' && deployPreview
      ? `${meta.description} Preview: ${deployPreview.message}`
      : action === 'rollback-cidr' && rollbackStamp
        ? `${meta.description} Копия: ${rollbackStamp}.`
        : meta.description

  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => {
        if (!open && !loading) onClose()
      }}
      title={meta.title}
      description={description}
      confirmLabel={meta.confirmLabel}
      destructive={meta.destructive}
      loading={loading}
      onConfirm={onConfirm}
      alert={
        meta.destructive
          ? {
              variant: 'warning',
              title: meta.alertTitle || 'Внимание',
              children: 'Операция может занять несколько минут. Не закрывайте вкладку до завершения.',
            }
          : undefined
      }
    />
  )
}
