import type { LucideIcon } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

type DialogSize = 'sm' | 'md' | 'lg' | 'xl'

const sizeClasses: Record<DialogSize, string> = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-5xl w-[min(96vw,64rem)]',
}

const heightClasses: Record<DialogSize, string> = {
  sm: 'max-h-[min(90dvh,36rem)]',
  md: 'max-h-[min(90dvh,40rem)]',
  lg: 'max-h-[min(90dvh,44rem)]',
  xl: 'max-h-[min(94dvh,56rem)]',
}

export interface AppDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: React.ReactNode
  description?: React.ReactNode
  icon?: LucideIcon
  footer?: React.ReactNode
  children?: React.ReactNode
  size?: DialogSize
  className?: string
  contentClassName?: string
  bodyClassName?: string
  hideClose?: boolean
}

export default function AppDialog({
  open,
  onOpenChange,
  title,
  description,
  icon: Icon,
  footer,
  children,
  size = 'lg',
  className,
  contentClassName,
  bodyClassName,
  hideClose,
}: AppDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={cn(
          'flex flex-col gap-0 overflow-hidden p-0',
          heightClasses[size],
          sizeClasses[size],
          className,
          contentClassName,
        )}
        hideClose={hideClose}
      >
        <DialogHeader className="shrink-0 space-y-1.5 border-b px-6 pb-3 pt-6 text-center sm:text-left">
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

        <div className={cn('min-h-0 flex-1 overflow-y-auto px-6 py-4', bodyClassName)}>
          {children}
        </div>

        {footer && (
          <DialogFooter className="shrink-0 border-t bg-background px-6 py-3 sm:space-x-2">
            {footer}
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}
