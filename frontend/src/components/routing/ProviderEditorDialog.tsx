import { useEffect, useState } from 'react'
import { FileText, Save } from 'lucide-react'
import {
  ApiError,
  getRoutingProviderContent,
  saveRoutingProviderContent,
} from '@/api/client'
import AppDialog from '@/components/shared/AppDialog'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useNotifications } from '@/context/NotificationContext'

interface ProviderEditorDialogProps {
  filename: string | null
  providerName?: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved?: () => void
}

export default function ProviderEditorDialog({
  filename,
  providerName,
  open,
  onOpenChange,
  onSaved,
}: ProviderEditorDialogProps) {
  const { success, error: notifyError } = useNotifications()
  const [content, setContent] = useState('')
  const [cidrCount, setCidrCount] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open || !filename) return
    setLoading(true)
    getRoutingProviderContent(filename)
      .then((data) => {
        setContent(data.content)
        setCidrCount(data.cidr_count)
      })
      .catch((err) =>
        notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки файла провайдера'),
      )
      .finally(() => setLoading(false))
  }, [open, filename, notifyError])

  const handleSave = async () => {
    if (!filename) return
    setSaving(true)
    try {
      const result = await saveRoutingProviderContent(filename, content)
      setCidrCount(result.cidr_count)
      success(`Файл ${providerName || filename} сохранён`)
      onSaved?.()
      onOpenChange(false)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  return (
    <AppDialog
      open={open}
      onOpenChange={onOpenChange}
      title={
        <span className="flex items-center gap-2">
          <FileText size={18} />
          {providerName || filename || 'Провайдер'}
        </span>
      }
      description={
        filename
          ? `Редактирование ${filename}${cidrCount != null ? ` · ${cidrCount} CIDR` : ''}`
          : undefined
      }
      footer={
        <>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Отмена
          </Button>
          <Button onClick={() => void handleSave()} disabled={loading || saving || !filename}>
            <Save size={14} className="mr-1" />
            {saving ? 'Сохранение...' : 'Сохранить'}
          </Button>
        </>
      }
    >
      {loading ? (
        <Spinner label="Загрузка содержимого..." className="py-12" />
      ) : (
        <Textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          className="min-h-[24rem] font-mono text-xs"
          spellCheck={false}
        />
      )}
    </AppDialog>
  )
}
