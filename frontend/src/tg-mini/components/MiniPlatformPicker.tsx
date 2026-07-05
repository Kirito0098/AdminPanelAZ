import { cn } from '@/lib/utils'
import { INSTALL_PLATFORMS, PLATFORM_ICONS } from '@/tg-mini/lib/platformMeta'
import type { InstallPlatform } from '@/types'

interface MiniPlatformPickerProps {
  value: InstallPlatform
  onChange: (value: InstallPlatform) => void
  label?: string
}

export default function MiniPlatformPicker({ value, onChange, label = 'Устройство' }: MiniPlatformPickerProps) {
  const activeLabel = INSTALL_PLATFORMS.find((item) => item.value === value)?.label ?? value

  return (
    <div className="tg-mini-platform-picker">
      <p className="tg-mini-platform-hint">
        Пошаговая инструкция для <strong>{activeLabel}</strong>
      </p>
      <div className="tg-mini-platform-grid tg-mini-platform-grid--balanced" role="radiogroup" aria-label={label}>
        {INSTALL_PLATFORMS.map((option) => {
          const active = value === option.value
          const Icon = PLATFORM_ICONS[option.value]
          return (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={active}
              aria-label={option.label}
              className={cn('tg-mini-platform-option', active && 'is-active')}
              onClick={() => onChange(option.value)}
            >
              <span className="tg-mini-platform-icon-wrap">
                <Icon size={18} className="shrink-0" aria-hidden />
              </span>
              <span>{option.label}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

export { guessInstallPlatform } from '@/tg-mini/lib/platformMeta'
