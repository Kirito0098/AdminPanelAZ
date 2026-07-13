import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import {
  ApiError,
  deleteTelegramWebhook,
  getAdminNotifySettings,
  getTelegramLinkCode,
  getTelegramSettings,
  getUsers,
  registerTelegramWebhook,
  testAdminNotify,
  testAdminNotifyEvent,
  testNocReportPreview,
  testNocWeeklyImagePreview,
  testTelegram,
  updateAdminNotifySettings,
  updateTelegramSettings,
  updateUser,
} from '@/api/client'
import { useNotifications } from '@/context/NotificationContext'
import type { AdminNotifySettings, TelegramSettings, User } from '@/types'

export type TelegramAuthMethod = 'oidc' | 'legacy'

export type TelegramSection = 'setup' | 'bot' | 'miniapp' | 'interactive' | 'notify'

export function useTelegramSettings() {
  const { success, error: notifyError } = useNotifications()
  const [settings, setSettings] = useState<TelegramSettings | null>(null)
  const [adminNotify, setAdminNotify] = useState<AdminNotifySettings | null>(null)
  const [botToken, setBotToken] = useState('')
  const [botUsername, setBotUsername] = useState('')
  const [authMaxAge, setAuthMaxAge] = useState('300')
  const [authMethod, setAuthMethod] = useState<TelegramAuthMethod>('legacy')
  const [oidcClientId, setOidcClientId] = useState('')
  const [oidcClientSecret, setOidcClientSecret] = useState('')
  const [chatIds, setChatIds] = useState<string[]>([])
  const [telegramId, setTelegramId] = useState('')
  const [notifyRecipientIds, setNotifyRecipientIds] = useState<number[]>([])
  const [notifyEnabled, setNotifyEnabled] = useState(false)
  const [notifyOnBackup, setNotifyOnBackup] = useState(false)
  const [interactiveEnabled, setInteractiveEnabled] = useState(false)
  const [eventToggles, setEventToggles] = useState<Record<string, boolean>>({})
  const [nodeOfflineGraceMinutes, setNodeOfflineGraceMinutes] = useState('3')
  const [saving, setSaving] = useState(false)
  const [savingInteractive, setSavingInteractive] = useState(false)
  const [savingNotify, setSavingNotify] = useState(false)
  const [loading, setLoading] = useState(true)
  const [testing, setTesting] = useState(false)
  const [testingNotify, setTestingNotify] = useState(false)
  const [testingNotifyEvent, setTestingNotifyEvent] = useState<string | null>(null)
  const [testingNocReport, setTestingNocReport] = useState<'daily' | 'weekly' | 'image' | null>(null)
  const [registeringWebhook, setRegisteringWebhook] = useState(false)
  const [deletingWebhook, setDeletingWebhook] = useState(false)
  const [linkCode, setLinkCode] = useState<string | null>(null)
  const [linkedAdmins, setLinkedAdmins] = useState<User[]>([])
  const [linkedAccounts, setLinkedAccounts] = useState<User[]>([])
  const [unlinkingUserId, setUnlinkingUserId] = useState<number | null>(null)

  const applyUsers = useCallback((users: User[]) => {
    const linked = users.filter((user) => Boolean(user.telegram_id?.trim()))
    setLinkedAccounts(linked)
    setLinkedAdmins(linked.filter((user) => user.role === 'admin'))
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [tg, notify, users] = await Promise.all([
        getTelegramSettings(),
        getAdminNotifySettings(),
        getUsers().catch(() => [] as User[]),
      ])
      applyUsers(users)
      setSettings(tg)
      setBotUsername(tg.bot_username)
      setAuthMaxAge(String(tg.auth_max_age_seconds || 300))
      setAuthMethod(tg.auth_method === 'oidc' ? 'oidc' : 'legacy')
      setOidcClientId(tg.oidc_client_id || '')
      setChatIds(tg.chat_ids?.length ? tg.chat_ids : tg.chat_id ? [tg.chat_id] : [])
      setNotifyEnabled(tg.notify_enabled)
      setNotifyOnBackup(tg.notify_on_backup)
      setInteractiveEnabled(tg.interactive_enabled)
      setAdminNotify(notify)
      setTelegramId(notify.telegram_id)
      setNotifyRecipientIds(notify.recipient_user_ids ?? [])
      setEventToggles(Object.fromEntries(notify.events.map((e) => [e.key, e.enabled])))
      setNodeOfflineGraceMinutes(String(Math.max(1, Math.round((notify.node_offline_grace_seconds ?? 180) / 60))))
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
    }
  }, [notifyError, applyUsers])

  useEffect(() => {
    void load()
  }, [load])

  const loginConfigured = Boolean(settings?.login_ready)
  const oidcLoginReady = Boolean(
    settings?.auth_method === 'oidc' && settings?.oidc_client_id && settings?.oidc_client_secret_set,
  )
  const legacyLoginReady = Boolean(
    settings?.auth_method === 'legacy' &&
      settings?.legacy_login_enabled &&
      settings?.bot_token_set &&
      settings?.bot_username,
  )
  const miniAppReady = Boolean(settings?.mini_app_url)
  const webhookReady = Boolean(settings?.webhook_registered)
  const notifyEventsEnabled = useMemo(
    () => Object.values(eventToggles).filter(Boolean).length,
    [eventToggles],
  )
  const hasNotifyRecipients = notifyRecipientIds.length > 0 || Boolean(telegramId.trim())
  const hasBackupRecipients = chatIds.length > 0

  const handleSaveBot = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const maxAge = Number.parseInt(authMaxAge, 10)
      const updated = await updateTelegramSettings({
        bot_token: botToken || undefined,
        bot_username: botUsername.trim() || undefined,
        auth_method: authMethod,
        auth_max_age_seconds: authMethod === 'legacy' && Number.isFinite(maxAge) ? maxAge : undefined,
        oidc_client_id: authMethod === 'oidc' ? oidcClientId.trim() || undefined : undefined,
        oidc_client_secret: authMethod === 'oidc' && oidcClientSecret ? oidcClientSecret : undefined,
      })
      setSettings(updated)
      setBotUsername(updated.bot_username)
      setAuthMaxAge(String(updated.auth_max_age_seconds))
      setAuthMethod(updated.auth_method === 'oidc' ? 'oidc' : 'legacy')
      setOidcClientId(updated.oidc_client_id || '')
      setOidcClientSecret('')
      setBotToken('')
      success('Настройки бота сохранены')
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
      const graceMinutes = Math.max(1, Math.min(1440, Number.parseInt(nodeOfflineGraceMinutes, 10) || 3))
      const [updated, updatedTg] = await Promise.all([
        updateAdminNotifySettings({
          recipient_user_ids: notifyRecipientIds,
          events: eventToggles,
          node_offline_grace_seconds: graceMinutes * 60,
        }),
        updateTelegramSettings({
          chat_ids: chatIds,
          notify_enabled: notifyEnabled,
          notify_on_backup: notifyOnBackup,
        }),
      ])
      setAdminNotify(updated)
      setSettings(updatedTg)
      setTelegramId(updated.telegram_id)
      setNotifyRecipientIds(updated.recipient_user_ids ?? [])
      setChatIds(updatedTg.chat_ids?.length ? updatedTg.chat_ids : updatedTg.chat_id ? [updatedTg.chat_id] : [])
      setNotifyEnabled(updatedTg.notify_enabled)
      setNotifyOnBackup(updatedTg.notify_on_backup)
      setEventToggles(Object.fromEntries(updated.events.map((item) => [item.key, item.enabled])))
      setNodeOfflineGraceMinutes(String(Math.max(1, Math.round((updated.node_offline_grace_seconds ?? 180) / 60))))
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
      notifyError(err instanceof ApiError ? err.message : 'Не удалось подключить бота к панели')
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
      notifyError(err instanceof ApiError ? err.message : 'Не удалось отключить бота от панели')
    } finally {
      setDeletingWebhook(false)
    }
  }

  const handleGetLinkCode = async () => {
    try {
      const result = await getTelegramLinkCode()
      setLinkCode(result.code)
      const command = `/link ${result.code}`
      try {
        await navigator.clipboard.writeText(command)
        success(`Код скопирован (действует ${result.expires_in_seconds} сек)`)
      } catch {
        success(`Код привязки создан (действует ${result.expires_in_seconds} сек)`)
      }
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

  const handleUnlinkTelegram = async (user: User) => {
    setUnlinkingUserId(user.id)
    try {
      await updateUser(user.id, { telegram_id: '' })
      const tgId = user.telegram_id?.trim()
      setLinkedAccounts((prev) => prev.filter((item) => item.id !== user.id))
      setLinkedAdmins((prev) => prev.filter((item) => item.id !== user.id))
      setNotifyRecipientIds((prev) => prev.filter((id) => id !== user.id))
      if (tgId) {
        setChatIds((prev) => prev.filter((id) => id !== tgId))
      }
      if (telegramId === tgId) {
        setTelegramId('')
      }
      success(`Telegram отвязан от ${user.username}`)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось отвязать Telegram')
    } finally {
      setUnlinkingUserId(null)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    try {
      await testTelegram()
      success('Тестовое сообщение отправлено получателям бэкапов')
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
      success('Тестовое уведомление отправлено выбранным получателям')
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
      success(result.message || 'NOC сводка отправлена выбранным получателям')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка отправки')
    } finally {
      setTestingNocReport(null)
    }
  }

  const handleTestNocWeeklyImage = async () => {
    setTestingNocReport('image')
    try {
      const result = await testNocWeeklyImagePreview()
      success(result.message || 'NOC weekly изображение отправлено выбранным получателям')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка отправки изображения')
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
    authMethod,
    setAuthMethod,
    oidcClientId,
    setOidcClientId,
    oidcClientSecret,
    setOidcClientSecret,
    chatIds,
    setChatIds,
    telegramId,
    setTelegramId,
    notifyRecipientIds,
    setNotifyRecipientIds,
    hasNotifyRecipients,
    hasBackupRecipients,
    notifyEnabled,
    setNotifyEnabled,
    notifyOnBackup,
    setNotifyOnBackup,
    interactiveEnabled,
    eventToggles,
    setEventToggles,
    nodeOfflineGraceMinutes,
    setNodeOfflineGraceMinutes,
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
    linkedAdmins,
    linkedAccounts,
    unlinkingUserId,
    load,
    loginConfigured,
    oidcLoginReady,
    legacyLoginReady,
    miniAppReady,
    webhookReady,
    notifyEventsEnabled,
    handleSaveBot,
    handleCopyMiniAppUrl,
    handleSaveAdminNotify,
    handleSaveInteractive,
    handleRegisterWebhook,
    handleDeleteWebhook,
    handleGetLinkCode,
    handleCopyLinkCode,
    handleUnlinkTelegram,
    handleTest,
    handleTestAdminNotify,
    handleTestNotifyEvent,
    handleTestNocReport,
    handleTestNocWeeklyImage,
  }
}

export type TelegramSettingsHook = ReturnType<typeof useTelegramSettings>
