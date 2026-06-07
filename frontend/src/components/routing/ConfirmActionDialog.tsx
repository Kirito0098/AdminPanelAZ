import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { ConfirmAction } from './useRoutingPage'

const confirmMeta: Record<
  Exclude<ConfirmAction, null>,
  { title: string; description: string; confirmLabel: string; destructive?: boolean }
> = {
  'apply-doall': {
    title: 'Применить маршрутизацию?',
    description:
      'Будет выполнен doall.sh на активном узле. Это может занять несколько минут и перезагрузить правила маршрутизации.',
    confirmLabel: 'Выполнить doall.sh',
    destructive: true,
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
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{meta.title}</DialogTitle>
          <DialogDescription>{meta.description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            Отмена
          </Button>
          <Button
            variant={meta.destructive ? 'destructive' : 'default'}
            onClick={onConfirm}
            disabled={loading}
          >
            {meta.confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
