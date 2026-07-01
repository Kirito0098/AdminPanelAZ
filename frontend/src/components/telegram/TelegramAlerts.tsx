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
        <SettingsAlert variant="warning" title="Сначала настройте бота">
          Укажите токен и имя бота на вкладке <strong>Данные бота</strong> — без этого не заработают вход,
          приложение и команды.
        </SettingsAlert>
      )}

      {tg.interactiveEnabled && !tg.webhookReady && tg.settings.bot_token_set && (
        <SettingsAlert variant="warning" title="Команды бота не подключены">
          Вы включили ответы бота, но связь с панелью ещё не настроена. Нажмите «Подключить бота» на вкладке{' '}
          <strong>Команды бота</strong> (нужен доступ к панели по HTTPS из интернета).
        </SettingsAlert>
      )}

      {tg.notifyEnabled && !tg.telegramId && (
        <SettingsAlert variant="info" title="Укажите свой Telegram ID">
          Уведомления включены, но некуда отправлять — заполните ID на вкладке <strong>Уведомления</strong> или в{' '}
          <Link to="/settings" className="font-medium text-primary underline-offset-4 hover:underline">
            Настройки → Пользователи
          </Link>
          .
        </SettingsAlert>
      )}

      {!tg.notifyEnabled && tg.notifyEventsEnabled > 0 && (
        <SettingsAlert variant="info" title="Уведомления сохранены, но выключены">
          Вы выбрали типы событий, но общий переключатель выключен. Включите его на вкладке{' '}
          <strong>Данные бота</strong>.
        </SettingsAlert>
      )}
    </div>
  )
}
