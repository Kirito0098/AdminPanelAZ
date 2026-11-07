import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'

type ToggleRowProps = {
  id: string
  label: string
  description?: string
  checked: boolean
  disabled?: boolean
  onCheckedChange: (checked: boolean) => void
}

export default function ToggleRow({
  id,
  label,
  description,
  checked,
  disabled,
  onCheckedChange,
}: ToggleRowProps) {
  return (
    <div
      className={cn(
        'flex items-start justify-between gap-4 rounded-xl border bg-card/50 p-4 transition-colors',
        checked && !disabled && 'border-primary/20 bg-primary/5',
        disabled && 'opacity-60',
      )}
    >
      <div className="min-w-0 space-y-1">
        <Label htmlFor={id} className={cn('font-medium', !disabled && 'cursor-pointer')}>
          {label}
        </Label>
        {description && <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>}
      </div>
      <Switch id={id} checked={checked} disabled={disabled} onCheckedChange={onCheckedChange} />
    </div>
  )
}
