import { CheckCircle2, AlertCircle, AlertTriangle, Info, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ToastItem } from '@/context/NotificationContext'
import { Button } from './button'

const icons = {
  success: CheckCircle2,
  error: AlertCircle,
  warning: AlertTriangle,
  info: Info,
}

const styles = {
  success:
    'border-emerald-500/40 bg-emerald-500/10 text-emerald-800 shadow-emerald-500/10 dark:text-emerald-300',
  error: 'border-destructive/40 bg-destructive/10 text-destructive shadow-destructive/10',
  warning:
    'border-amber-500/40 bg-amber-500/10 text-amber-800 shadow-amber-500/10 dark:text-amber-300',
  info: 'border-primary/40 bg-primary/10 text-primary shadow-primary/10',
}

const iconStyles = {
  success: 'text-emerald-600 dark:text-emerald-400',
  error: 'text-destructive',
  warning: 'text-amber-600 dark:text-amber-400',
  info: 'text-primary',
}

interface ToastProps {
  toast: ToastItem
  onDismiss: (id: string) => void
}

export default function Toast({ toast, onDismiss }: ToastProps) {
  const Icon = icons[toast.type]

  return (
    <div
      className={cn(
        'pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-lg border p-4 shadow-lg backdrop-blur-sm',
        'animate-in slide-in-from-right-full fade-in duration-300',
        styles[toast.type],
      )}
      role="alert"
    >
      <Icon className={cn('mt-0.5 h-5 w-5 shrink-0', iconStyles[toast.type])} />
      <p className="flex-1 text-sm font-medium leading-snug">{toast.message}</p>
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6 shrink-0 opacity-70 hover:opacity-100"
        onClick={() => onDismiss(toast.id)}
        aria-label="Закрыть"
      >
        <X className="h-4 w-4" />
      </Button>
    </div>
  )
}
