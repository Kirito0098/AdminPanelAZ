import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Power, Puzzle } from 'lucide-react'
import { ApiError, updateFeatureToggles } from '@/api/client'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Button } from '@/components/ui/button'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'

export default function TelegramDisableSection() {
  const { isEnabled, refresh } = useFeatureModules()
  const { success, error: notifyError } = useNotifications()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [disabling, setDisabling] = useState(false)

  if (!isEnabled('telegram')) {
    return null
  }

  const handleDisable = async () => {
    setDisabling(true)
    try {
      await updateFeatureToggles({ telegram: false })
      await refresh()
      success('Telegram отключён. Webhook снят, перезапустите панель для полного применения.')
      setConfirmOpen(false)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось отключить модуль')
    } finally {
      setDisabling(false)
    }
  }

  return (
    <>
      <SettingsAlert variant="info" title="Отключить Telegram?">
        <p>
          Если интеграция не нужна, можно выключить модуль — панель перестанет принимать сообщения от бота и
          открывать приложение в Telegram. Все настройки сохранятся, их можно включить снова позже.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="secondary" onClick={() => setConfirmOpen(true)}>
            <Power className="mr-1.5 h-4 w-4" />
            Отключить Telegram
          </Button>
          <Button type="button" size="sm" variant="outline" asChild>
            <Link to="/settings">
              <Puzzle className="mr-1.5 h-4 w-4" />
              Все модули
            </Link>
          </Button>
        </div>
      </SettingsAlert>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Отключить интеграцию Telegram?"
        description="Бот перестанет отвечать на команды и присылать уведомления. Для полного применения может понадобиться перезапуск панели."
        confirmLabel="Отключить"
        destructive
        loading={disabling}
        onConfirm={() => void handleDisable()}
        alert={{
          variant: 'warning',
          title: 'После отключения',
          children: 'Перезапустите сервис панели (systemctl restart adminpanelaz). Раздел Telegram исчезнет из меню.',
        }}
      />
    </>
  )
}
