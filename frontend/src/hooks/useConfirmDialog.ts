import { useCallback, useState } from 'react'
import type { ConfirmDialogAlert, ConfirmDialogProps } from '@/components/shared/ConfirmDialog'

type ConfirmOptions = Omit<ConfirmDialogProps, 'open' | 'onOpenChange' | 'onConfirm'> & {
  onConfirm: () => void | Promise<void>
}

const defaultState: ConfirmOptions | null = null

export function useConfirmDialog() {
  const [options, setOptions] = useState<ConfirmOptions | null>(defaultState)
  const [loading, setLoading] = useState(false)

  const confirm = useCallback((opts: ConfirmOptions) => {
    setOptions(opts)
    setLoading(false)
  }, [])

  const close = useCallback(() => {
    if (loading) return
    setOptions(null)
  }, [loading])

  const handleConfirm = useCallback(async () => {
    if (!options) return
    setLoading(true)
    try {
      await options.onConfirm()
      setOptions(null)
    } finally {
      setLoading(false)
    }
  }, [options])

  const dialogProps: ConfirmDialogProps | null = options
    ? {
        ...options,
        open: true,
        onOpenChange: (open) => !open && close(),
        loading,
        onConfirm: handleConfirm,
      }
    : null

  return { confirm, close, dialogProps, isOpen: options !== null }
}

export type { ConfirmDialogAlert }
