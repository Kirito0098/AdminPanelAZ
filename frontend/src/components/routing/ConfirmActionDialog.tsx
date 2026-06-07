import { Loader2 } from 'lucide-react'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import type { ConfirmAction } from './useRoutingPage'

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
    title: 'Сгенерировать CIDR из БД?',
    description:
      'Списки AP-*-include-ips.txt будут пересобраны из локальной SQLite БД без обращения к интернету.',
    confirmLabel: 'Сгенерировать',
  },
  'generate-doall': {
    title: 'Сгенерировать и применить?',
    description:
      'CIDR-файлы будут сгенерированы из БД, затем автоматически выполнен doall.sh. Операция длительная.',
    confirmLabel: 'Сгенерировать + doall',
    destructive: true,
    alertTitle: 'Длительная операция',
  },
}

interface ConfirmActionDialogProps {
  action: ConfirmAction
  onClose: () => void
  onConfirm: () => void
  loading?: boolean
}

export default function ConfirmActionDialog({ action, onClose, onConfirm, loading }: ConfirmActionDialogProps) {
  if (!action) return null
  const meta = confirmMeta[action]

  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => {
        if (!open && !loading) onClose()
      }}
      title={meta.title}
      description={meta.description}
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
