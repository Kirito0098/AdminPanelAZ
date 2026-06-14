import { Link } from 'react-router-dom'
import SettingsAlert from '@/components/settings/SettingsAlert'
import type { TelegramSettingsHook } from './useTelegramSettings'

interface TelegramAlertsProps {
  tg: TelegramSettingsHook
}

export default function TelegramAlerts({ tg }: TelegramAlertsProps) {
  if (tg.loading || !tg.settings) return null

  return (
    <div className="space-y-3">
      {!tg.settings.bot_token_set && (
        <SettingsAlert variant="warning" title="Бот не настроен">
          Укажите токен и username на вкладке <strong>Бот</strong> — без них недоступны вход, Mini App и webhook.
        </SettingsAlert>
      )}

      {tg.interactiveEnabled && !tg.webhookReady && tg.settings.bot_token_set && (
        <SettingsAlert variant="warning" title="Webhook не зарегистрирован">
          Интерактивный бот включён, но webhook не активен. Зарегистрируйте его на вкладке{' '}
          <strong>Интерактив</strong> (нужен публичный HTTPS).
        </SettingsAlert>
      )}

      {tg.notifyEnabled && !tg.telegramId && (
        <SettingsAlert variant="info" title="Telegram ID не указан">
          Глобальные уведомления включены, но ваш ID пуст — события не будут доставляться. Заполните на вкладке{' '}
          <strong>Уведомления</strong> или в{' '}
          <Link to="/settings" className="font-medium text-primary underline-offset-4 hover:underline">
            Настройки → Пользователи
          </Link>
          .
        </SettingsAlert>
      )}

      {!tg.notifyEnabled && tg.notifyEventsEnabled > 0 && (
        <SettingsAlert variant="info" title="Подписки сохранены, доставка выключена">
          Включите глобальный переключатель уведомлений на вкладке <strong>Бот</strong>.
        </SettingsAlert>
      )}
    </div>
  )
}
