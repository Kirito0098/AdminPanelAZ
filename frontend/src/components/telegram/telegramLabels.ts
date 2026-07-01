import type { TelegramSection } from './useTelegramSettings'

export const TELEGRAM_TAB_META: Record<
  TelegramSection,
  { label: string; shortLabel: string; description: string }
> = {
  setup: {
    label: 'С чего начать',
    shortLabel: 'Старт',
    description: 'Пошаговая инструкция: создайте бота, привяжите аккаунт и проверьте вход в панель',
  },
  bot: {
    label: 'Данные бота',
    shortLabel: 'Бот',
    description: 'Токен и имя бота из BotFather — основа для входа, приложения и сообщений',
  },
  miniapp: {
    label: 'Приложение',
    shortLabel: 'Прилож.',
    description: 'Откройте панель прямо в Telegram — кнопка меню у вашего бота',
  },
  interactive: {
    label: 'Команды бота',
    shortLabel: 'Команды',
    description: 'Бот отвечает на /start, /status и другие команды в чате',
  },
  notify: {
    label: 'Уведомления',
    shortLabel: 'Увед.',
    description: 'Сообщения о важных событиях приходят вам в личку от бота',
  },
}
