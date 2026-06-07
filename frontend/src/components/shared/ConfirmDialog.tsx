import type { LucideIcon } from 'lucide-react'
import { Loader2 } from 'lucide-react'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

type AlertVariant = 'warning' | 'danger' | 'info'

export interface ConfirmDialogAlert {
  variant: AlertVariant
  title?: string
  children: React.ReactNode
}

export interface ConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: React.ReactNode
  icon?: LucideIcon
  alert?: ConfirmDialogAlert
  cancelLabel?: string
  confirmLabel?: string
  destructive?: boolean
  loading?: boolean
  onConfirm: () => void | Promise<void>
  children?: React.ReactNode
  className?: string
}

export default function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  icon: Icon,
  alert,
  cancelLabel = 'Отмена',
  confirmLabel = 'Подтвердить',
  destructive = false,
  loading = false,
  onConfirm,
  children,
  className,
}: ConfirmDialogProps) {
  const handleConfirm = () => {
    void onConfirm()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn('max-w-lg', className)}>
        <DialogHeader>
          <DialogTitle className={Icon ? 'flex items-center gap-2' : undefined}>
            {Icon && <Icon className="h-5 w-5 shrink-0 text-muted-foreground" />}
            {title}
          </DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>

        {alert && (
          <SettingsAlert variant={alert.variant} title={alert.title}>
            {alert.children}
          </SettingsAlert>
        )}

        {children}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button variant={destructive ? 'destructive' : 'default'} onClick={handleConfirm} disabled={loading}>
            {loading ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Выполнение...
              </>
            ) : (
              confirmLabel
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function ConfirmDialogHost({ dialogProps }: { dialogProps: ConfirmDialogProps | null }) {
  if (!dialogProps) return null
  return <ConfirmDialog {...dialogProps} />
}
