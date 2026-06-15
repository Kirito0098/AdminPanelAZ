import { useEffect, useState } from 'react'
import { Globe } from 'lucide-react'
import { ApiError, getGeoRoutingHint } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Badge } from '@/components/ui/badge'
import type { GeoRoutingHint } from '@/types'

export default function GeoRoutingHintBanner({ enabled }: { enabled: boolean }) {
  const [hint, setHint] = useState<GeoRoutingHint | null>(null)

  useEffect(() => {
    if (!enabled) {
      setHint(null)
      return
    }
    void getGeoRoutingHint()
      .then(setHint)
      .catch((err: unknown) => {
        if (err instanceof ApiError) setHint(null)
      })
  }, [enabled])

  if (!enabled || !hint?.hint_message) return null

  return (
    <SettingsAlert variant="info" title="Geo-routing подсказка">
      <div className="flex flex-wrap items-center gap-2">
        <Globe size={14} className="shrink-0 text-primary" />
        <span>{hint.hint_message}</span>
        {hint.recommended_node_name && (
          <Badge variant="secondary" className="text-[10px]">
            {hint.recommended_node_name}
          </Badge>
        )}
        {hint.client_geo_label && (
          <span className="text-xs text-muted-foreground">· ваш регион: {hint.client_geo_label}</span>
        )}
      </div>
    </SettingsAlert>
  )
}
