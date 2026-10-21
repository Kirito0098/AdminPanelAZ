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
          Укажите токен и имя бота на вкладке <strong>Бот и авторизация</strong> — без этого не заработают вход,
          приложение и команды.
        </SettingsAlert>
      )}

      {tg.interactiveEnabled && !tg.commandsConnected && tg.settings.bot_token_set && (
        <SettingsAlert variant="warning" title="Команды бота не подключены">
          Вы включили ответы бота, но связь с панелью ещё не настроена. Нажмите «Подключить бота» на вкладке{' '}
          <strong>Команды бота</strong> (нужен доступ к панели по HTTPS из интернета) или включите{' '}
          <strong>Связь через узел</strong>, если панель в РФ.
        </SettingsAlert>
      )}

      {tg.interactiveEnabled && tg.settings.bot_token_set && tg.relayError && (
        <SettingsAlert variant="danger" title="Связь с Telegram через узел не работает">
          {tg.relayError} — пока узел не ответит, бот не получит команды. Проверьте узлы на вкладке{' '}
          <strong>Связь через узел</strong>.
        </SettingsAlert>
      )}

      {tg.notifyOnBackup && !tg.hasBackupRecipients && (
        <SettingsAlert variant="info" title="Укажите получателей бэкапов">
          Отправка архивов включена — выберите администраторов на вкладке <strong>Уведомления</strong>.
        </SettingsAlert>
      )}

      {tg.notifyEnabled && !tg.hasNotifyRecipients && (
        <SettingsAlert variant="info" title="Укажите получателей уведомлений">
          Уведомления включены, но некуда отправлять — выберите администраторов на вкладке{' '}
          <strong>Уведомления</strong> или привяжите Telegram в{' '}
          <Link to="/settings/users" className="font-medium text-primary underline-offset-4 hover:underline">
            Настройки → Пользователи
          </Link>
          .
        </SettingsAlert>
      )}

      {!tg.notifyEnabled && tg.notifyEventsEnabled > 0 && (
        <SettingsAlert variant="info" title="Уведомления сохранены, но выключены">
          Вы выбрали типы событий, но общий переключатель выключен. Включите его на вкладке{' '}
          <strong>Уведомления</strong>.
        </SettingsAlert>
      )}
    </div>
  )
}
