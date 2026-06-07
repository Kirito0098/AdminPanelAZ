import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface SpinnerProps {
  label?: string
  className?: string
}

export default function Spinner({ label, className }: SpinnerProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-3 text-muted-foreground', className)}>
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
      {label && <p className="text-sm">{label}</p>}
    </div>
  )
}
