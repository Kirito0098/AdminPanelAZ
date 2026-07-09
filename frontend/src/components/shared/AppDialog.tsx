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

type DialogSize = 'sm' | 'md' | 'lg'

const sizeClasses: Record<DialogSize, string> = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
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
  hideClose,
}: AppDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn(sizeClasses[size], className, contentClassName)} hideClose={hideClose}>
        <DialogHeader>
          <DialogTitle className={Icon ? 'flex items-center gap-2' : undefined}>
            {Icon && <Icon className="h-5 w-5 shrink-0 text-muted-foreground" />}
            {title}
          </DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>

        {children}

        {footer && <DialogFooter>{footer}</DialogFooter>}
      </DialogContent>
    </Dialog>
  )
}
