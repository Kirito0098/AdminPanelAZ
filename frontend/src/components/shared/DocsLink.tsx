import { BookOpen, ExternalLink } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface DocsLinkProps {
  href: string
  label?: string
  /** `inline` — text link; `button` — outline chip for headers */
  variant?: 'inline' | 'button'
  className?: string
  showIcon?: boolean
}

/**
 * External link to a panel guide on GitHub (`docs/*.md`).
 */
export default function DocsLink({
  href,
  label = 'Инструкция',
  variant = 'inline',
  className,
  showIcon = true,
}: DocsLinkProps) {
  if (variant === 'button') {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className={cn(
          'inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-input bg-background px-3 text-sm font-medium text-foreground shadow-sm transition-colors hover:bg-accent hover:text-accent-foreground',
          className,
        )}
      >
        {showIcon ? <BookOpen size={14} aria-hidden /> : null}
        {label}
        <ExternalLink size={12} className="opacity-60" aria-hidden />
      </a>
    )
  }

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        'inline-flex items-center gap-1 text-xs font-medium text-primary underline-offset-2 hover:underline',
        className,
      )}
    >
      {showIcon ? <BookOpen size={12} aria-hidden /> : null}
      {label}
      <ExternalLink size={11} className="opacity-70" aria-hidden />
    </a>
  )
}
