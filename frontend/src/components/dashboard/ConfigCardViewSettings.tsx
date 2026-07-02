import { Pipette, SlidersHorizontal } from 'lucide-react'
import { useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import {
  ACCENT_OPTIONS,
  DEFAULT_CONFIG_CARD_VIEW_PREFS,
  DEFAULT_CUSTOM_BUTTON_COLOR,
  FIELD_LABELS,
  GRID_COLS_OPTIONS,
  isValidHexColor,
  normalizeHexColor,
  type CardButtonAccent,
  type CardGridCols,
  type ConfigCardFieldVisibility,
  type ConfigCardViewPrefs,
} from '@/lib/configCardViewPrefs'
import { cn } from '@/lib/utils'

interface ConfigCardViewSettingsProps {
  prefs: ConfigCardViewPrefs
  onChange: (prefs: ConfigCardViewPrefs) => void
}

const FIELD_KEYS = Object.keys(
  DEFAULT_CONFIG_CARD_VIEW_PREFS.fields,
) as (keyof ConfigCardFieldVisibility)[]

export default function ConfigCardViewSettings({ prefs, onChange }: ConfigCardViewSettingsProps) {
  const colorInputRef = useRef<HTMLInputElement>(null)
  const customColor = normalizeHexColor(prefs.customButtonColor) ?? DEFAULT_CUSTOM_BUTTON_COLOR

  const setGridCols = (gridCols: CardGridCols) => {
    onChange({ ...prefs, gridCols })
  }

  const setButtonAccent = (buttonAccent: CardButtonAccent) => {
    onChange({ ...prefs, buttonAccent })
  }

  const setCustomColor = (value: string) => {
    const normalized = normalizeHexColor(value)
    if (!normalized) return
    onChange({
      ...prefs,
      buttonAccent: 'custom',
      customButtonColor: normalized,
    })
  }

  const toggleField = (key: keyof ConfigCardFieldVisibility, checked: boolean) => {
    onChange({
      ...prefs,
      fields: { ...prefs.fields, [key]: checked },
    })
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="h-10 w-10 shrink-0 border-primary/25 bg-primary/15 text-primary hover:bg-primary/20"
          aria-label="Настройки карточек"
          title="Настройки карточек"
        >
          <SlidersHorizontal size={16} />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72 p-3">
        <DropdownMenuLabel className="px-0 text-xs font-medium text-muted-foreground">
          Столбцы
        </DropdownMenuLabel>
        <div className="mb-3 flex flex-wrap items-center gap-1 rounded-xl border bg-muted/30 p-1">
          {GRID_COLS_OPTIONS.map((option) => (
            <Button
              key={option.value}
              type="button"
              size="sm"
              variant={prefs.gridCols === option.value ? 'default' : 'ghost'}
              className="h-7 flex-1 px-2 text-xs"
              onClick={() => setGridCols(option.value)}
            >
              {option.label}
            </Button>
          ))}
        </div>

        <DropdownMenuSeparator className="my-2" />

        <DropdownMenuLabel className="px-0 text-xs font-medium text-muted-foreground">
          Показывать
        </DropdownMenuLabel>
        <div className="mb-3 max-h-48 space-y-2 overflow-y-auto pr-1">
          {FIELD_KEYS.map((key) => (
            <label
              key={key}
              className="flex cursor-pointer items-center gap-2 text-xs leading-none"
            >
              <Checkbox
                checked={prefs.fields[key]}
                onCheckedChange={(checked) => toggleField(key, checked === true)}
              />
              <span>{FIELD_LABELS[key]}</span>
            </label>
          ))}
        </div>

        <DropdownMenuSeparator className="my-2" />

        <DropdownMenuLabel className="px-0 text-xs font-medium text-muted-foreground">
          Цвет кнопок
        </DropdownMenuLabel>
        <div className="flex flex-wrap items-center gap-2">
          {ACCENT_OPTIONS.map((option) => {
            const active = prefs.buttonAccent === option.value
            return (
              <button
                key={option.value}
                type="button"
                title={option.label}
                aria-label={option.label}
                aria-pressed={active}
                onClick={() => setButtonAccent(option.value)}
                className={cn(
                  'flex h-8 w-8 items-center justify-center rounded-md border-2 transition-all',
                  active ? 'border-primary ring-2 ring-primary/30' : 'border-transparent hover:border-muted-foreground/30',
                )}
              >
                <span className={cn('h-5 w-5 rounded-sm border', option.swatchClass)} />
              </button>
            )
          })}
          <button
            type="button"
            title="Свой цвет"
            aria-label="Свой цвет"
            aria-pressed={prefs.buttonAccent === 'custom'}
            onClick={() => {
              setButtonAccent('custom')
              colorInputRef.current?.click()
            }}
            className={cn(
              'relative flex h-8 w-8 items-center justify-center overflow-hidden rounded-md border-2 transition-all',
              prefs.buttonAccent === 'custom'
                ? 'border-primary ring-2 ring-primary/30'
                : 'border-transparent hover:border-muted-foreground/30',
            )}
          >
            <span
              className="h-5 w-5 rounded-sm border border-white/20"
              style={{ backgroundColor: customColor }}
            />
            <Pipette size={10} className="absolute bottom-0.5 right-0.5 text-white drop-shadow" />
          </button>
          <input
            ref={colorInputRef}
            type="color"
            value={customColor}
            onChange={(e) => setCustomColor(e.target.value)}
            className="sr-only"
            tabIndex={-1}
            aria-hidden
          />
        </div>
        {prefs.buttonAccent === 'custom' && (
          <div className="mt-2 flex items-center gap-2">
            <label className="relative h-8 w-8 shrink-0 cursor-pointer overflow-hidden rounded-md border">
              <span
                className="block h-full w-full"
                style={{ backgroundColor: customColor }}
              />
              <input
                type="color"
                value={customColor}
                onChange={(e) => setCustomColor(e.target.value)}
                className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                aria-label="Выбрать цвет"
              />
            </label>
            <Input
              value={prefs.customButtonColor}
              onChange={(e) => {
                const next = e.target.value
                onChange({ ...prefs, buttonAccent: 'custom', customButtonColor: next })
              }}
              onBlur={() => {
                if (!isValidHexColor(prefs.customButtonColor)) {
                  onChange({ ...prefs, customButtonColor: customColor })
                } else {
                  setCustomColor(prefs.customButtonColor)
                }
              }}
              placeholder="#00bcd4"
              className="h-8 font-mono text-xs"
              spellCheck={false}
            />
          </div>
        )}
        <p className="mt-2 text-[10px] leading-snug text-muted-foreground">
          «По умолчанию» — VPN cyan, AntiZapret amber. Остальные и свой цвет — единый акцент всех кнопок.
        </p>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
