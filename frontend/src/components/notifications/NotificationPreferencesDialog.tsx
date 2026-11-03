import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Switch } from '@/components/ui/switch'
import { CATEGORY_LABEL } from '@/components/notifications/labels'
import {
  fetchNotificationPreferences,
  saveNotificationPreferences,
  type NotificationCategory,
} from '@/api/notifications'

const CATEGORIES: NotificationCategory[] = ['requests', 'security', 'nodes', 'services', 'tasks']

const ALL_ON: Record<NotificationCategory, boolean> = {
  requests: true,
  security: true,
  nodes: true,
  services: true,
  tasks: true,
}

export default function NotificationPreferencesDialog({
  open,
  onOpenChange,
  onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved: () => void
}) {
  const [categories, setCategories] = useState(ALL_ON)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setError('')
    fetchNotificationPreferences()
      .then((prefs) => {
        if (!cancelled) setCategories((prev) => ({ ...prev, ...prefs.categories }))
      })
      .catch(() => {
        if (!cancelled) setError('Не удалось загрузить настройки')
      })
    return () => {
      cancelled = true
    }
  }, [open])

  const save = async () => {
    if (saving) return
    setSaving(true)
    setError('')
    try {
      await saveNotificationPreferences({ categories })
      onSaved()
      onOpenChange(false)
    } catch {
      setError('Не удалось сохранить настройки')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Уведомления в панели</DialogTitle>
          <DialogDescription>
            Какие категории показывать в колокольчике. Telegram настраивается отдельно, на странице
            «Telegram».
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3 py-2">
          {CATEGORIES.map((key) => (
            <label key={key} className="flex items-center justify-between gap-3 text-sm">
              <span>{CATEGORY_LABEL[key]}</span>
              <Switch
                checked={categories[key]}
                onCheckedChange={(checked) =>
                  setCategories((prev) => ({ ...prev, [key]: checked }))
                }
                aria-label={CATEGORY_LABEL[key]}
              />
            </label>
          ))}
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Отмена
          </Button>
          <Button onClick={() => void save()} disabled={saving}>
            {saving ? 'Сохранение…' : 'Сохранить'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
