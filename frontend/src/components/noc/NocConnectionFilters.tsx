import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'

export type MinDurationFilter = 'any' | '15m' | '1h' | '4h'
export type NocSortKey = 'client' | 'traffic' | 'time' | 'rate' | 'duration'

type NocConnectionFiltersProps = {
  showNodeFilter: boolean
  filterNode: string
  filterCity: string
  filterIsp: string
  minDuration: MinDurationFilter
  sortKey: NocSortKey
  nodeOptions: string[]
  cityOptions: string[]
  ispOptions: string[]
  onFilterNode: (v: string) => void
  onFilterCity: (v: string) => void
  onFilterIsp: (v: string) => void
  onMinDuration: (v: MinDurationFilter) => void
  onSortKey: (v: NocSortKey) => void
  className?: string
}

const ALL = '__all__'
const NONE = '__none__'

export default function NocConnectionFilters({
  showNodeFilter,
  filterNode,
  filterCity,
  filterIsp,
  minDuration,
  sortKey,
  nodeOptions,
  cityOptions,
  ispOptions,
  onFilterNode,
  onFilterCity,
  onFilterIsp,
  onMinDuration,
  onSortKey,
  className,
}: NocConnectionFiltersProps) {
  return (
    <div
      className={cn(
        'flex gap-3 overflow-x-auto pb-1 sm:flex-wrap sm:overflow-visible',
        className,
      )}
    >
      {showNodeFilter && (
        <div className="min-w-[140px] space-y-1">
          <Label className="text-[11px] text-muted-foreground">Узел</Label>
          <Select value={filterNode || ALL} onValueChange={(v) => onFilterNode(v === ALL ? '' : v)}>
            <SelectTrigger className="h-8 text-xs">
              <SelectValue placeholder="Все" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Все</SelectItem>
              {nodeOptions.map((name) => (
                <SelectItem key={name} value={name}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
      <div className="min-w-[140px] space-y-1">
        <Label className="text-[11px] text-muted-foreground">Город</Label>
        <Select value={filterCity || ALL} onValueChange={(v) => onFilterCity(v === ALL ? '' : v)}>
          <SelectTrigger className="h-8 text-xs">
            <SelectValue placeholder="Все" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Все</SelectItem>
            <SelectItem value={NONE}>без гео</SelectItem>
            {cityOptions.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="min-w-[140px] space-y-1">
        <Label className="text-[11px] text-muted-foreground">ISP</Label>
        <Select value={filterIsp || ALL} onValueChange={(v) => onFilterIsp(v === ALL ? '' : v)}>
          <SelectTrigger className="h-8 text-xs">
            <SelectValue placeholder="Все" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Все</SelectItem>
            <SelectItem value={NONE}>без ISP</SelectItem>
            {ispOptions.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="min-w-[120px] space-y-1">
        <Label className="text-[11px] text-muted-foreground">Длительность</Label>
        <Select value={minDuration} onValueChange={(v) => onMinDuration(v as MinDurationFilter)}>
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">любая</SelectItem>
            <SelectItem value="15m">&gt;15м</SelectItem>
            <SelectItem value="1h">&gt;1ч</SelectItem>
            <SelectItem value="4h">&gt;4ч</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="min-w-[140px] space-y-1">
        <Label className="text-[11px] text-muted-foreground">Сортировка</Label>
        <Select value={sortKey} onValueChange={(v) => onSortKey(v as NocSortKey)}>
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="traffic">трафик</SelectItem>
            <SelectItem value="rate">скорость</SelectItem>
            <SelectItem value="duration">длительность</SelectItem>
            <SelectItem value="time">активность</SelectItem>
            <SelectItem value="client">имя</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  )
}

export const NOC_FILTER_NONE = NONE

export function minDurationSeconds(filter: MinDurationFilter): number | null {
  if (filter === '15m') return 15 * 60
  if (filter === '1h') return 3600
  if (filter === '4h') return 4 * 3600
  return null
}
