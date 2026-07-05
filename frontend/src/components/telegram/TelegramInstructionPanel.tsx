import { useState } from 'react'
import { ChevronDown, type LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface TelegramInstructionPanelProps {
  title?: string
  description?: string
  icon?: LucideIcon
  defaultOpen?: boolean
  children: React.ReactNode
}

export default function TelegramInstructionPanel({
  title = 'Инструкция',
  description,
  icon: Icon,
  defaultOpen = false,
  children,
}: TelegramInstructionPanelProps) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className="rounded-lg border bg-muted/20">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-start gap-3 p-4 text-left transition-colors hover:bg-muted/30"
      >
        {Icon && <Icon size={16} className="mt-0.5 shrink-0 text-muted-foreground" />}
        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-sm font-medium">{title}</p>
          {description && <p className="text-xs text-muted-foreground">{description}</p>}
        </div>
        <ChevronDown
          size={18}
          className={cn('mt-0.5 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')}
          aria-hidden
        />
      </button>
      {open && <div className="space-y-5 border-t px-4 pb-4 pt-4">{children}</div>}
    </div>
  )
}
