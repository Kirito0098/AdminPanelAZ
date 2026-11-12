import type { TelegramSection } from './useTelegramSettings'

export const TELEGRAM_TAB_META: Record<
  TelegramSection,
  { label: string; shortLabel: string; description: string }
> = {
  bot: {
    label: 'Бот и авторизация',
    shortLabel: 'Бот',
    description: 'Токен BotFather, Legacy или OIDC для входа — пошаговая инструкция и форма настройки',
  },
  miniapp: {
    label: 'Приложение',
    shortLabel: 'Прилож.',
    description: 'Mini App в Telegram: настройка кнопки, привязка аккаунта и возможности для user/admin',
  },
  interactive: {
    label: 'Команды бота',
    shortLabel: 'Команды',
    description: 'Webhook, команды /start и /status, заявки на доступ из Telegram',
  },
  relay: {
    label: 'Связь через узел',
    shortLabel: 'Узел',
    description: 'Для панели в РФ: запросы к Telegram через ваш зарубежный VPN-сервер',
  },
  notify: {
    label: 'Уведомления',
    shortLabel: 'Увед.',
    description: 'Получатели, переключатели, типы событий и NOC-сводки',
  },
}
