import { cn } from '@/lib/utils'
import { INSTALL_PLATFORMS, PLATFORM_ICONS } from '@/tg-mini/lib/platformMeta'
import type { InstallPlatform } from '@/types'

interface MiniPlatformPickerProps {
  value: InstallPlatform
  onChange: (value: InstallPlatform) => void
  label?: string
}

export default function MiniPlatformPicker({ value, onChange, label = 'Инструкция для' }: MiniPlatformPickerProps) {
  return (
    <div className="space-y-2">
      <p className="tg-mini-sheet-label">{label}</p>
      <div className="tg-mini-platform-grid" role="radiogroup" aria-label={label}>
        {INSTALL_PLATFORMS.map((option) => {
          const active = value === option.value
          const Icon = PLATFORM_ICONS[option.value]
          return (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={active}
              className={cn('tg-mini-platform-option', active && 'is-active')}
              onClick={() => onChange(option.value)}
            >
              <Icon size={16} className="shrink-0 opacity-80" aria-hidden />
              <span>{option.label}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

export { guessInstallPlatform } from '@/tg-mini/lib/platformMeta'
