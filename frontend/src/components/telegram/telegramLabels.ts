import type { TelegramSection } from './useTelegramSettings'

export const TELEGRAM_TAB_META: Record<
  TelegramSection,
  { label: string; shortLabel: string; description: string }
> = {
  setup: {
    label: 'С чего начать',
    shortLabel: 'Старт',
    description: 'Пошаговая инструкция: создайте бота, настройте вход и проверьте авторизацию',
  },
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
    description: 'Webhook, команды /start и /status, привязка аккаунта через /link',
  },
  notify: {
    label: 'Уведомления',
    shortLabel: 'Увед.',
    description: 'Получатели, переключатели, типы событий и NOC-сводки',
  },
}
