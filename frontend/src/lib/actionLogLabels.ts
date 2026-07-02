/** Русские подписи для кодов действий в журнале аудита. */
const ACTION_LOG_LABELS: Record<string, string> = {
  // Авторизация
  login_success: 'Успешный вход',
  login_failed: 'Неудачный вход',
  password_change: 'Смена пароля',
  '2fa_enable': 'Включение 2FA',
  '2fa_disable': 'Отключение 2FA',
  passkey_register: 'Регистрация passkey',
  passkey_delete: 'Удаление passkey',
  passkey_login_failed: 'Неудачный вход по passkey',
  telegram_link: 'Привязка Telegram',

  // Пользователи
  user_create: 'Создание пользователя',
  user_update: 'Изменение пользователя',
  user_delete: 'Удаление пользователя',

  // Узлы
  node_create: 'Создание узла',
  node_update: 'Изменение узла',
  node_delete: 'Удаление узла',
  node_activate: 'Активация узла',
  node_update_apply: 'Применение обновления узла',
  node_restart_agent: 'Перезапуск node agent',
  node_update_roll_queued: 'Откат обновления узла в очереди',
  node_api_key_rotate: 'Ротация API-ключа узла',
  node_mtls_enable: 'Включение mTLS узла',
  node_default_policy_update: 'Изменение политики узла по умолчанию',
  node_offline: 'Узел недоступен',
  node_sync_drift: 'Расхождение синхронизации узла',

  // Конфигурации
  config_create: 'Создание конфигурации',
  config_delete: 'Удаление конфигурации',
  config_download: 'Скачивание конфигурации',
  config_recreate: 'Пересоздание конфигурации',

  // OpenVPN — клиенты
  openvpn_temp_block: 'Временная блокировка OpenVPN',
  openvpn_perm_block: 'Постоянная блокировка OpenVPN',
  openvpn_unblock: 'Разблокировка OpenVPN',
  openvpn_disconnect: 'Отключение OpenVPN',
  openvpn_traffic_limit_set: 'Установка лимита трафика OpenVPN',
  openvpn_traffic_limit_clear: 'Снятие лимита трафика OpenVPN',

  // WireGuard — клиенты
  wg_set_expiry: 'Изменение срока WireGuard',
  wg_temp_block: 'Временная блокировка WireGuard',
  wg_perm_block: 'Постоянная блокировка WireGuard',
  wg_unblock: 'Разблокировка WireGuard',
  wg_traffic_limit_set: 'Установка лимита трафика WireGuard',
  wg_traffic_limit_clear: 'Снятие лимита трафика WireGuard',

  // Уведомления (внутренние коды блокировок)
  temp_block: 'Временная блокировка',
  permanent_block: 'Постоянная блокировка',
  unblock: 'Разблокировка',

  // CIDR / маршрутизация
  settings_cidr_deploy: 'Развёртывание CIDR',
  settings_cidr_rollback_queued: 'Откат CIDR в очереди',
  settings_cidr_custom_provider: 'Изменение провайдера CIDR',
  settings_cidr_update_queued: 'Обновление CIDR в очереди',
  settings_cidr_db_refresh_queued: 'Обновление CIDR из базы в очереди',
  settings_cidr_db_clear: 'Очистка базы CIDR',
  settings_cidr_generate_from_db: 'Генерация CIDR из базы',

  // Настройки
  settings_change: 'Изменение настроек',
  settings_port_update: 'Изменение порта панели',
  settings_telegram_auth_update: 'Изменение авторизации Telegram',
  settings_telegram_update: 'Изменение настроек Telegram',
  settings_telegram_token: 'Изменение токена Telegram-бота',
  settings_telegram_test: 'Тест Telegram-уведомлений',
  settings_telegram_webhook: 'Изменение webhook Telegram',
  settings_nightly_update: 'Изменение ночного рестарта',
  settings_backup_update: 'Изменение настроек бэкапов',
  settings_backup_create: 'Создание бэкапа',
  settings_backup_restore: 'Восстановление из бэкапа',
  settings_backup_delete: 'Удаление бэкапа',
  settings_backup_test_telegram: 'Тест бэкапа в Telegram',
  settings_restart_service: 'Перезапуск службы',
  settings_user_password_update: 'Изменение пароля пользователя',
  settings_user_role_update: 'Изменение роли пользователя',
  settings_run_doall: 'Перегенерация конфигурации VPN',
  settings_recreate_profiles: 'Пересоздание профилей',
  settings_vpn_network_publish: 'Публикация панели в VPN-сети',
  settings_public_download_toggle: 'Переключение публичного скачивания',
  settings_monitor_update: 'Изменение мониторинга',
  settings_retention_update: 'Изменение срока хранения журналов',
  settings_antifilter_refresh: 'Обновление AntiFilter',
  settings_admin_notify_update: 'Изменение уведомлений администратора',
  settings_admin_notify_test: 'Тест уведомлений администратора',
  settings_security_update: 'Изменение настроек безопасности',
  settings_security_temp_whitelist: 'Временный whitelist IP',
  settings_security_temp_whitelist_remove: 'Удаление IP из whitelist',
  settings_security_unban: 'Разбан IP',

  // Безопасность / интеграции
  security_settings_update: 'Изменение безопасности',
  security_temp_whitelist: 'Временный whitelist IP',
  security_temp_whitelist_remove: 'Удаление IP из whitelist',
  event_webhook_settings_update: 'Изменение webhook событий',
  audit_stream_settings_update: 'Изменение потока аудита',
  audit_stream_test: 'Тест потока аудита',
  secrets_rotation_apply: 'Ротация секретов',

  // Система
  system_update_queued: 'Обновление системы в очереди',
  system_rebuild_queued: 'Пересборка frontend в очереди',
  system_restart: 'Перезапуск панели',
  backup_restore: 'Восстановление из бэкапа',
  edit_files_transfer: 'Передача файлов конфигурации',
  ha_replicate_partial_failure: 'Частичный сбой репликации HA',
}

export function actionLogLabel(action: string): string {
  const key = action.trim()
  if (!key) return '—'
  return ACTION_LOG_LABELS[key] ?? key.replace(/_/g, ' ')
}
