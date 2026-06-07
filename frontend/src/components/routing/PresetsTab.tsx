import { Layers } from 'lucide-react'
import EmptyState from '@/components/ui/EmptyState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { CidrPresetInfo, CidrProviderInfo } from '@/types'

interface PresetsTabProps {
  presets: CidrPresetInfo[]
  providers: CidrProviderInfo[]
  isAdmin: boolean
  actionLoading: boolean
  onApply: (key: string, name: string) => void
}

export default function PresetsTab({
  presets,
  providers,
  isAdmin,
  actionLoading,
  onApply,
}: PresetsTabProps) {
  if (presets.length === 0) {
    return (
      <EmptyState
        icon={Layers}
        title="Нет пресетов"
        description="Встроенные пресеты маршрутизации не найдены."
      />
    )
  }

  const providerName = (filename: string) =>
    providers.find((p) => p.filename === filename)?.name ?? filename

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {presets.map((preset) => (
        <Card key={preset.key} className="flex flex-col">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Layers size={16} className="text-primary" />
              {preset.name}
            </CardTitle>
            <CardDescription>{preset.description}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col gap-3">
            <div className="flex flex-wrap gap-1.5">
              {preset.providers.map((f) => (
                <Badge key={f} variant="outline" className="text-xs">
                  {providerName(f)}
                </Badge>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              Включает {preset.providers.length} провайдер(ов). Остальные будут отключены.
            </p>
            {isAdmin && (
              <Button
                size="sm"
                className="mt-auto w-fit"
                disabled={actionLoading}
                onClick={() => onApply(preset.key, preset.name)}
              >
                Применить пресет
              </Button>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
