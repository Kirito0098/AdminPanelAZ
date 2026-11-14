import { useCallback, useEffect, useState } from 'react'
import { useNotifications } from '@/context/NotificationContext'
import type { RoutingOverview } from '@/types'

/**
 * Provider-file selection shared by the pipeline and deploy forms.
 * `null` means "not initialized yet": once providers arrive, everything is selected.
 */
export function useProviderSelection(providers: RoutingOverview['providers'] | undefined) {
  const { error: notifyError } = useNotifications()
  const [selectedProviderFiles, setSelectedProviderFiles] = useState<string[] | null>(null)

  useEffect(() => {
    if (!providers?.length || selectedProviderFiles !== null) return
    setSelectedProviderFiles(providers.map((provider) => provider.filename))
  }, [providers, selectedProviderFiles])

  const resolveSelectedProviderPayload = useCallback(
    (files?: string[] | null): string[] | null | undefined => {
      const allCount = providers?.length ?? 0
      const targets = files ?? selectedProviderFiles ?? []
      if (targets.length === 0) {
        notifyError('Выберите хотя бы одного провайдера')
        return undefined
      }
      if (allCount > 0 && targets.length >= allCount) {
        return null
      }
      return targets
    },
    [providers?.length, notifyError, selectedProviderFiles],
  )

  return {
    selectedProviderFiles,
    setSelectedProviderFiles,
    resolveSelectedProviderPayload,
  }
}
