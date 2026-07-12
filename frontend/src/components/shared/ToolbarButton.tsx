import type { ReactNode } from 'react'
import { Button, type ButtonProps } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export interface ToolbarButtonProps {
  icon: ReactNode
  label: string
  shortLabel?: string
  onClick?: () => void
  disabled?: boolean
  variant?: ButtonProps['variant']
  size?: ButtonProps['size']
  className?: string
  type?: 'button' | 'submit' | 'reset'
}

export default function ToolbarButton({
  icon,
  label,
  shortLabel,
  onClick,
  disabled,
  variant = 'outline',
  size,
  className,
  type = 'button',
}: ToolbarButtonProps) {
  const showIconOnly = !shortLabel

  return (
    <Button
      type={type}
      variant={variant}
      size={size}
      className={cn('gap-2 touch-manipulation', showIconOnly && 'max-md:min-h-[44px] max-md:min-w-[44px]', className)}
      onClick={onClick}
      disabled={disabled}
      aria-label={showIconOnly ? label : undefined}
    >
      {icon}
      {shortLabel ? (
        <>
          <span className="sm:hidden">{shortLabel}</span>
          <span className="hidden sm:inline">{label}</span>
        </>
      ) : (
        <span className="hidden sm:inline">{label}</span>
      )}
    </Button>
  )
}
