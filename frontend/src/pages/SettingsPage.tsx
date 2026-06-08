import { FormEvent, useEffect, useState } from 'react'
import { Settings } from 'lucide-react'
import { ApiError, changePassword, createUser, deleteUser, getSettings, getUsers } from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import BackupTab from '@/components/settings/BackupTab'
import ConfigDeliveryTab from '@/components/settings/ConfigDeliveryTab'
import FeatureTogglesTab from '@/components/settings/FeatureTogglesTab'
import MaintenanceTab from '@/components/settings/MaintenanceTab'
import MonitoringTab from '@/components/settings/MonitoringTab'
import PersonalTab from '@/components/settings/PersonalTab'
import SecurityTab from '@/components/settings/SecurityTab'
import SettingsNav, {
  getDefaultSection,
  isSectionAvailable,
  type SettingsSection,
} from '@/components/settings/SettingsNav'
import TelegramTab from '@/components/settings/TelegramTab'
import TestsTab from '@/components/settings/TestsTab'
import UpdatesTab from '@/components/settings/UpdatesTab'
import UsersTab from '@/components/settings/UsersTab'
import VpnNetworkTab from '@/components/settings/VpnNetworkTab'
import { NodeBadge } from '@/components/NodeSelector'
import { useAuth } from '@/context/AuthContext'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { useTheme } from '@/context/ThemeContext'
import type { AppSettings, User, UserRole } from '@/types'

const SECTION_TITLES: Record<SettingsSection, { title: string; description: string }> = {
  personal: {
    title: 'Профиль',
    description: 'Тема интерфейса, смена пароля и двухфакторная аутентификация',
  },
  users: {
    title: 'Пользователи',
    description: 'Управление учётными записями, ролями и доступом viewer',
  },
  security: {
    title: 'Доступ к панели',
    description: 'IP whitelist, защита от сканеров и активные баны',
  },
  config_delivery: {
    title: 'Раздача конфигов',
    description: 'Одноразовые QR-ссылки и публичные route-файлы для роутеров',
  },
  maintenance: {
    title: 'Обслуживание',
    description: 'Пересоздание профилей, путь AntiZapret и перезапуск VPN-служб',
  },
  backup: {
    title: 'Резервные копии',
    description: 'Создание, восстановление и автоматизация бэкапов панели',
  },
  monitoring: {
    title: 'Мониторинг',
    description: 'Пороги CPU/RAM и интервалы Telegram-оповещений о нагрузке',
  },
  vpn_network: {
    title: 'Сеть и публикация',
    description: 'Публикация панели и reverse-proxy (фаза 17 — полный UI)',
  },
  telegram: {
    title: 'Telegram',
    description: 'Бот для оповещений администратора и доставки бэкапов',
  },
  modules: {
    title: 'Модули',
    description: 'Управление фоновыми задачами и разделами панели',
  },
  updates: {
    title: 'Обновления',
    description: 'Проверка и применение обновлений из git-репозитория',
  },
  tests: {
    title: 'Диагностика',
    description: 'Запуск smoke-тестов backend из панели',
  },
}

export default function SettingsPage() {
  const { user } = useAuth()
  const { isSettingsTabEnabled, isEnabled } = useFeatureModules()
  const { activeNode } = useNode()
  const { theme, setTheme } = useTheme()
  const { success, error: notifyError } = useNotifications()
  const { startGlobal, doneGlobal, inline } = useProgress()
  const { confirm, dialogProps } = useConfirmDialog()
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [users, setUsers] = useState<User[]>([])
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newRole, setNewRole] = useState<UserRole>('user')
  const [currentPwd, setCurrentPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const isAdmin = user?.role === 'admin'

  const [activeSection, setActiveSection] = useState<SettingsSection>(() => getDefaultSection(isAdmin))

  useEffect(() => {
    if (!isSectionAvailable(activeSection, isAdmin, isSettingsTabEnabled, isEnabled)) {
      setActiveSection(getDefaultSection(isAdmin))
    }
  }, [activeSection, isAdmin, isSettingsTabEnabled, isEnabled])

  const load = async () => {
    startGlobal()
    try {
      const s = await getSettings()
      setSettings(s)
      if (isAdmin) {
        setUsers(await getUsers())
      }
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки настроек')
    } finally {
      doneGlobal()
    }
  }

  useEffect(() => {
    load()
  }, [user?.role, activeNode?.id])

  const handleCreateUser = async (e: FormEvent) => {
    e.preventDefault()
    const createdName = newUsername.trim()
    if (!createdName) {
      notifyError('Укажите логин')
      return
    }
    if (!newPassword) {
      notifyError('Укажите пароль')
      return
    }
    try {
      await createUser({ username: createdName, password: newPassword, role: newRole })
      setNewUsername('')
      setNewPassword('')
      setUsers(await getUsers())
      success(`Пользователь «${createdName}» создан`)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка создания пользователя')
    }
  }

  const handleDeleteUser = (id: number, name: string) => {
    confirm({
      title: 'Удалить пользователя?',
      description: (
        <>
          Учётная запись «<strong>{name}</strong>» будет удалена без возможности восстановления.
        </>
      ),
      confirmLabel: 'Удалить',
      destructive: true,
      onConfirm: async () => {
        try {
          await deleteUser(id)
          setUsers(await getUsers())
          success(`Пользователь «${name}» удалён`)
        } catch (err) {
          notifyError(err instanceof ApiError ? err.message : 'Ошибка удаления')
        }
      },
    })
  }

  const handleChangePassword = async (e: FormEvent) => {
    e.preventDefault()
    if (!currentPwd) {
      notifyError('Укажите текущий пароль')
      return
    }
    if (!newPwd || newPwd.length < 4) {
      notifyError('Новый пароль: минимум 4 символа')
      return
    }
    try {
      await changePassword(currentPwd, newPwd)
      setCurrentPwd('')
      setNewPwd('')
      success('Пароль изменён')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка смены пароля')
    }
  }

  const sectionMeta = SECTION_TITLES[activeSection]

  const renderSection = () => {
    switch (activeSection) {
      case 'personal':
        return (
          <PersonalTab
            theme={theme}
            onThemeChange={setTheme}
            currentPwd={currentPwd}
            newPwd={newPwd}
            onCurrentPwdChange={setCurrentPwd}
            onNewPwdChange={setNewPwd}
            onChangePassword={handleChangePassword}
          />
        )
      case 'users':
        return (
          <UsersTab
            users={users}
            currentUserId={user?.id}
            newUsername={newUsername}
            newPassword={newPassword}
            newRole={newRole}
            onNewUsernameChange={setNewUsername}
            onNewPasswordChange={setNewPassword}
            onNewRoleChange={setNewRole}
            onCreateUser={handleCreateUser}
            onDeleteUser={handleDeleteUser}
          />
        )
      case 'security':
        return <SecurityTab />
      case 'config_delivery':
        return <ConfigDeliveryTab />
      case 'maintenance':
        return <MaintenanceTab settings={settings} />
      case 'backup':
        return <BackupTab />
      case 'monitoring':
        return <MonitoringTab />
      case 'telegram':
        return <TelegramTab />
      case 'modules':
        return <FeatureTogglesTab />
      case 'updates':
        return <UpdatesTab />
      case 'tests':
        return <TestsTab />
      case 'vpn_network':
        return <VpnNetworkTab />
      default:
        return null
    }
  }

  return (
    <div className="space-y-6">
      <ConfirmDialogHost dialogProps={dialogProps} />
      <div className="flex items-start gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Settings size={22} />
        </div>
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-2xl font-bold tracking-tight">Настройки</h2>
            <NodeBadge name={activeNode?.name ?? settings?.node_name} status={activeNode?.status} />
          </div>
          <p className="text-sm text-muted-foreground">
            {isAdmin
              ? 'Учётная запись, безопасность, операции и параметры системы'
              : 'Тема интерфейса, смена пароля и двухфакторная аутентификация'}
          </p>
        </div>
      </div>

      <InlineProgressBar active={inline.active} label={inline.label} />

      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
        <aside className="w-full shrink-0 lg:sticky lg:top-4 lg:w-64">
          <div className="rounded-lg border bg-card p-2">
            <SettingsNav
              active={activeSection}
              onChange={setActiveSection}
              isAdmin={isAdmin}
              isTabEnabled={isSettingsTabEnabled}
              isModuleEnabled={isEnabled}
            />
          </div>
        </aside>

        <main className="min-w-0 flex-1 space-y-4">
          <div className="rounded-lg border bg-muted/30 px-4 py-3">
            <h3 className="text-lg font-semibold tracking-tight">{sectionMeta.title}</h3>
            <p className="text-sm text-muted-foreground">{sectionMeta.description}</p>
          </div>
          {renderSection()}
        </main>
      </div>
    </div>
  )
}
