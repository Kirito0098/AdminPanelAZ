import { Gamepad2 } from 'lucide-react'
import EmptyState from '@/components/ui/EmptyState'
import StatusPanel from '@/components/noc/StatusPanel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { GameFilterItem } from '@/types'

interface GameFiltersTabProps {
  games: GameFilterItem[]
  gameModes: Record<string, string>
  isAdmin: boolean
  actionLoading: boolean
  onModeChange: (key: string, mode: string) => void
  onSync: () => void
}

const modeLabels: Record<string, string> = {
  none: 'Не задано',
  include: 'Включить',
  exclude: 'Исключить',
}

export default function GameFiltersTab({
  games,
  gameModes,
  isAdmin,
  actionLoading,
  onModeChange,
  onSync,
}: GameFiltersTabProps) {
  if (games.length === 0) {
    return (
      <EmptyState
        icon={Gamepad2}
        title="Нет игровых фильтров"
        description="API игровых фильтров не вернул данных или сервис недоступен."
      />
    )
  }

  return (
    <StatusPanel title="Игровые фильтры" icon={Gamepad2}>
      <p className="mb-4 text-sm text-muted-foreground">
        Домены и IP игровых серверов → AZ-Game-include-* в config AntiZapret. Режим «Включить»
        добавляет трафик в маршрутизацию, «Исключить» — убирает из неё.
      </p>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {games.map((g) => (
          <div
            key={g.key}
            className="flex items-center justify-between gap-3 rounded-lg border p-4"
          >
            <div className="min-w-0">
              <div className="font-medium text-sm truncate">{g.title}</div>
              <div className="text-xs text-muted-foreground truncate">{g.subtitle}</div>
              {g.domains.length > 0 && (
                <div className="mt-1 text-[10px] text-muted-foreground truncate">
                  {g.domains.slice(0, 3).join(', ')}
                  {g.domains.length > 3 && ` +${g.domains.length - 3}`}
                </div>
              )}
            </div>
            {isAdmin ? (
              <Select
                value={gameModes[g.key] || 'none'}
                onValueChange={(v) => onModeChange(g.key, v)}
              >
                <SelectTrigger className="w-[130px] h-8 text-xs shrink-0">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">—</SelectItem>
                  <SelectItem value="include">Включить</SelectItem>
                  <SelectItem value="exclude">Исключить</SelectItem>
                </SelectContent>
              </Select>
            ) : (
              <Badge variant="outline">{modeLabels[gameModes[g.key] || 'none']}</Badge>
            )}
          </div>
        ))}
      </div>

      {isAdmin && (
        <Button className="mt-6" disabled={actionLoading} onClick={onSync}>
          Синхронизировать и применить
        </Button>
      )}
    </StatusPanel>
  )
}
