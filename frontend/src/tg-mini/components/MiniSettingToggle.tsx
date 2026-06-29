import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'

interface MiniSettingToggleProps {
  label: string
  description?: string
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  disabled?: boolean
  className?: string
}

export default function MiniSettingToggle({
  label,
  description,
  checked,
  onCheckedChange,
  disabled = false,
  className,
}: MiniSettingToggleProps) {
  return (
    <div className={cn('tg-mini-setting-row', className)}>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium leading-snug">{label}</p>
        {description && <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{description}</p>}
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} disabled={disabled} aria-label={label} />
    </div>
  )
}
