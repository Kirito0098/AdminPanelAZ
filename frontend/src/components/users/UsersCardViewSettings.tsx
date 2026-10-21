import { SlidersHorizontal } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { GRID_COLS_OPTIONS } from '@/lib/configCardViewPrefs'
import {
  USERS_CARD_FIELD_LABELS,
  type UsersCardFieldKey,
  type UsersCardViewPrefs,
} from '@/lib/usersCardViewPrefs'

interface UsersCardViewSettingsProps {
  prefs: UsersCardViewPrefs
  onChange: (prefs: UsersCardViewPrefs) => void
}

const FIELD_KEYS = Object.keys(USERS_CARD_FIELD_LABELS) as UsersCardFieldKey[]

export default function UsersCardViewSettings({ prefs, onChange }: UsersCardViewSettingsProps) {
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
              onClick={() => onChange({ ...prefs, gridCols: option.value })}
            >
              {option.label}
            </Button>
          ))}
        </div>

        <DropdownMenuSeparator className="my-2" />

        <DropdownMenuLabel className="px-0 text-xs font-medium text-muted-foreground">
          Показывать
        </DropdownMenuLabel>
        <div className="max-h-56 space-y-2 overflow-y-auto pr-1">
          {FIELD_KEYS.map((key) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={prefs.fields[key]}
                onCheckedChange={(checked) =>
                  onChange({ ...prefs, fields: { ...prefs.fields, [key]: checked === true } })
                }
              />
              <span className="text-muted-foreground">{USERS_CARD_FIELD_LABELS[key]}</span>
            </label>
          ))}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
