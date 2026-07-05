import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import {
  ApiError,
  deleteTelegramWebhook,
  getAdminNotifySettings,
  getTelegramLinkCode,
  getTelegramSettings,
  registerTelegramWebhook,
  testAdminNotify,
  testAdminNotifyEvent,
  testNocReportPreview,
  testNocWeeklyPdfPreview,
  testTelegram,
  updateAdminNotifySettings,
  updateTelegramSettings,
} from '@/api/client'
import { useNotifications } from '@/context/NotificationContext'
import type { AdminNotifySettings, TelegramSettings } from '@/types'

export type TelegramSection = 'setup' | 'bot' | 'miniapp' | 'interactive' | 'notify'

export function useTelegramSettings() {
  const { success, error: notifyError } = useNotifications()
  const [settings, setSettings] = useState<TelegramSettings | null>(null)
  const [adminNotify, setAdminNotify] = useState<AdminNotifySettings | null>(null)
  const [botToken, setBotToken] = useState('')
  const [botUsername, setBotUsername] = useState('')
  const [authMaxAge, setAuthMaxAge] = useState('300')
  const [chatId, setChatId] = useState('')
  const [telegramId, setTelegramId] = useState('')
  const [notifyEnabled, setNotifyEnabled] = useState(false)
  const [notifyOnBackup, setNotifyOnBackup] = useState(false)
  const [interactiveEnabled, setInteractiveEnabled] = useState(false)
  const [eventToggles, setEventToggles] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState(false)
  const [savingInteractive, setSavingInteractive] = useState(false)
  const [savingNotify, setSavingNotify] = useState(false)
  const [loading, setLoading] = useState(true)
  const [testing, setTesting] = useState(false)
  const [testingNotify, setTestingNotify] = useState(false)
  const [testingNotifyEvent, setTestingNotifyEvent] = useState<string | null>(null)
  const [testingNocReport, setTestingNocReport] = useState<'daily' | 'weekly' | 'pdf' | null>(null)
  const [registeringWebhook, setRegisteringWebhook] = useState(false)
  const [deletingWebhook, setDeletingWebhook] = useState(false)
  const [linkCode, setLinkCode] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [tg, notify] = await Promise.all([getTelegramSettings(), getAdminNotifySettings()])
      setSettings(tg)
      setBotUsername(tg.bot_username)
      setAuthMaxAge(String(tg.auth_max_age_seconds || 300))
      setChatId(tg.chat_id)
      setNotifyEnabled(tg.notify_enabled)
      setNotifyOnBackup(tg.notify_on_backup)
      setInteractiveEnabled(tg.interactive_enabled)
      setAdminNotify(notify)
      setTelegramId(notify.telegram_id)
      setEventToggles(Object.fromEntries(notify.events.map((e) => [e.key, e.enabled])))
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
    }
  }, [notifyError])

  useEffect(() => {
    void load()
  }, [load])

  const loginConfigured = Boolean(settings?.bot_token_set && settings?.bot_username)
  const miniAppReady = Boolean(settings?.mini_app_url)
  const webhookReady = Boolean(settings?.webhook_registered)
  const notifyEventsEnabled = useMemo(
    () => Object.values(eventToggles).filter(Boolean).length,
    [eventToggles],
  )

  const handleSave = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const maxAge = Number.parseInt(authMaxAge, 10)
      const updated = await updateTelegramSettings({
        bot_token: botToken || undefined,
        bot_username: botUsername.trim() || undefined,
        auth_max_age_seconds: Number.isFinite(maxAge) ? maxAge : undefined,
        chat_id: chatId,
        notify_enabled: notifyEnabled,
        notify_on_backup: notifyOnBackup,
      })
      setSettings(updated)
      setBotUsername(updated.bot_username)
      setAuthMaxAge(String(updated.auth_max_age_seconds))
      setNotifyEnabled(updated.notify_enabled)
      setNotifyOnBackup(updated.notify_on_backup)
      setBotToken('')
      success('Настройки Telegram сохранены')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  const handleCopyMiniAppUrl = async () => {
    const url = settings?.mini_app_url
    if (!url) return
    try {
      await navigator.clipboard.writeText(url)
      success('Ссылка Mini App скопирована')
    } catch {
      notifyError('Не удалось скопировать ссылку')
    }
  }

  const handleSaveAdminNotify = async (e: FormEvent) => {
    e.preventDefault()
    setSavingNotify(true)
    try {
      const updated = await updateAdminNotifySettings({
        telegram_id: telegramId,
        events: eventToggles,
      })
      setAdminNotify(updated)
      setTelegramId(updated.telegram_id)
      setEventToggles(Object.fromEntries(updated.events.map((item) => [item.key, item.enabled])))
      success('Настройки уведомлений сохранены')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSavingNotify(false)
    }
  }

  const handleSaveInteractive = async (enabled: boolean) => {
    setSavingInteractive(true)
    try {
      const updated = await updateTelegramSettings({ interactive_enabled: enabled })
      setSettings(updated)
      setInteractiveEnabled(updated.interactive_enabled)
      success(enabled ? 'Интерактивный бот включён' : 'Интерактивный бот выключен')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
      setInteractiveEnabled(settings?.interactive_enabled ?? false)
    } finally {
      setSavingInteractive(false)
    }
  }

  const handleRegisterWebhook = async () => {
    setRegisteringWebhook(true)
    try {
      const updated = await registerTelegramWebhook()
      setSettings(updated)
      success('Webhook зарегистрирован')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка регистрации webhook')
    } finally {
      setRegisteringWebhook(false)
    }
  }

  const handleDeleteWebhook = async () => {
    setDeletingWebhook(true)
    try {
      const updated = await deleteTelegramWebhook()
      setSettings(updated)
      success('Webhook удалён')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка удаления webhook')
    } finally {
      setDeletingWebhook(false)
    }
  }

  const handleGetLinkCode = async () => {
    try {
      const result = await getTelegramLinkCode()
      setLinkCode(result.code)
      success(`Код привязки создан (действует ${result.expires_in_seconds} сек)`)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка получения кода')
    }
  }

  const handleCopyLinkCode = async () => {
    if (!linkCode) return
    try {
      await navigator.clipboard.writeText(`/link ${linkCode}`)
      success('Команда /link скопирована')
    } catch {
      notifyError('Не удалось скопировать')
    }
  }

  const handleTest = async () => {
    setTesting(true)
    try {
      await testTelegram()
      success('Тестовое сообщение отправлено в chat_id')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка отправки')
    } finally {
      setTesting(false)
    }
  }

  const handleTestAdminNotify = async () => {
    setTestingNotify(true)
    try {
      await testAdminNotify()
      success('Тестовое уведомление отправлено на ваш Telegram ID')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка отправки')
    } finally {
      setTestingNotify(false)
    }
  }

  const handleTestNotifyEvent = async (eventKey: string) => {
    setTestingNotifyEvent(eventKey)
    try {
      const result = await testAdminNotifyEvent(eventKey)
      success(result.message || 'Пример уведомления отправлен')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка отправки')
    } finally {
      setTestingNotifyEvent(null)
    }
  }

  const handleTestNocReport = async (period: 'daily' | 'weekly') => {
    setTestingNocReport(period)
    try {
      const result = await testNocReportPreview(period)
      success(result.message || 'NOC сводка отправлена на ваш Telegram ID')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка отправки')
    } finally {
      setTestingNocReport(null)
    }
  }

  const handleTestNocWeeklyPdf = async () => {
    setTestingNocReport('pdf')
    try {
      const result = await testNocWeeklyPdfPreview()
      success(result.message || 'NOC weekly PDF отправлен на ваш Telegram ID')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка отправки PDF')
    } finally {
      setTestingNocReport(null)
    }
  }

  return {
    settings,
    adminNotify,
    botToken,
    setBotToken,
    botUsername,
    setBotUsername,
    authMaxAge,
    setAuthMaxAge,
    chatId,
    setChatId,
    telegramId,
    setTelegramId,
    notifyEnabled,
    setNotifyEnabled,
    notifyOnBackup,
    setNotifyOnBackup,
    interactiveEnabled,
    eventToggles,
    setEventToggles,
    saving,
    savingInteractive,
    savingNotify,
    loading,
    testing,
    testingNotify,
    testingNotifyEvent,
    testingNocReport,
    registeringWebhook,
    deletingWebhook,
    linkCode,
    load,
    loginConfigured,
    miniAppReady,
    webhookReady,
    notifyEventsEnabled,
    handleSave,
    handleCopyMiniAppUrl,
    handleSaveAdminNotify,
    handleSaveInteractive,
    handleRegisterWebhook,
    handleDeleteWebhook,
    handleGetLinkCode,
    handleCopyLinkCode,
    handleTest,
    handleTestAdminNotify,
    handleTestNotifyEvent,
    handleTestNocReport,
    handleTestNocWeeklyPdf,
  }
}

export type TelegramSettingsHook = ReturnType<typeof useTelegramSettings>
