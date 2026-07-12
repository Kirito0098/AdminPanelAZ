import type { FormEvent } from 'react'
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
  const handleOpenChange = (next: boolean) => {
    if (!next && loading) return
    onOpenChange(next)
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (loading) return
    void onConfirm()
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className={cn('max-w-lg', className)}>
        <DialogHeader>
          <DialogTitle className={Icon ? 'flex items-center gap-2' : undefined}>
            {Icon && <Icon className="h-5 w-5 shrink-0 text-muted-foreground" />}
            {title}
          </DialogTitle>
          {description ? (
            <DialogDescription>{description}</DialogDescription>
          ) : (
            <DialogDescription className="sr-only">{title}</DialogDescription>
          )}
        </DialogHeader>

        <form noValidate onSubmit={handleSubmit} className="space-y-4">
          {alert && (
            <SettingsAlert variant={alert.variant} title={alert.title}>
              {alert.children}
            </SettingsAlert>
          )}

          {children}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={loading}
            >
              {cancelLabel}
            </Button>
            <Button
              type="submit"
              variant={destructive ? 'destructive' : 'default'}
              disabled={loading}
            >
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
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function ConfirmDialogHost({ dialogProps }: { dialogProps: ConfirmDialogProps | null }) {
  if (!dialogProps) return null
  return <ConfirmDialog {...dialogProps} />
}
