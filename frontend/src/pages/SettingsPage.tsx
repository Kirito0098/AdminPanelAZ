import { FormEvent, useEffect, useState } from 'react'
import { Settings } from 'lucide-react'
import { ApiError, changePassword, createUser, deleteUser, getSettings, getUsers } from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import BackupTab from '@/components/settings/BackupTab'
import FeatureTogglesTab from '@/components/settings/FeatureTogglesTab'
import MaintenanceTab from '@/components/settings/MaintenanceTab'
import PersonalTab from '@/components/settings/PersonalTab'
import SecurityTab from '@/components/settings/SecurityTab'
import SettingsNav, {
  getDefaultSection,
  isSectionAvailable,
  type SettingsSection,
} from '@/components/settings/SettingsNav'
import TelegramTab from '@/components/settings/TelegramTab'
import TestsTab from '@/components/settings/TestsTab'
import TwoFactorTab from '@/components/settings/TwoFactorTab'
import UpdatesTab from '@/components/settings/UpdatesTab'
import UsersTab from '@/components/settings/UsersTab'
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
    title: 'Личные настройки',
    description: 'Тема интерфейса, путь AntiZapret и смена пароля',
  },
  maintenance: {
    title: 'Обслуживание',
    description: 'Пересоздание профилей и перезапуск VPN-служб на активном узле',
  },
  backup: {
    title: 'Резервные копии',
    description: 'Создание, восстановление и автоматизация бэкапов панели',
  },
  telegram: {
    title: 'Telegram',
    description: 'Бот для оповещений администратора и доставки бэкапов',
  },
  security: {
    title: 'Безопасность',
    description: 'Двухфакторная аутентификация, IP whitelist и защита от сканеров',
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
    title: 'Тесты',
    description: 'Запуск smoke-тестов backend из панели',
  },
  users: {
    title: 'Пользователи',
    description: 'Управление учётными записями и ролями доступа',
  },
}

export default function SettingsPage() {
  const { user } = useAuth()
  const { isSettingsTabEnabled } = useFeatureModules()
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
    if (!isSectionAvailable(activeSection, isAdmin, isSettingsTabEnabled)) {
      setActiveSection(getDefaultSection(isAdmin))
    }
  }, [activeSection, isAdmin, isSettingsTabEnabled])

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
    const createdName = newUsername
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
            settings={settings}
            currentPwd={currentPwd}
            newPwd={newPwd}
            onCurrentPwdChange={setCurrentPwd}
            onNewPwdChange={setNewPwd}
            onChangePassword={handleChangePassword}
          />
        )
      case 'maintenance':
        return <MaintenanceTab />
      case 'backup':
        return <BackupTab />
      case 'telegram':
        return <TelegramTab />
      case 'security':
        return (
          <div className="space-y-4">
            <TwoFactorTab />
            <SecurityTab />
          </div>
        )
      case 'modules':
        return <FeatureTogglesTab />
      case 'updates':
        return <UpdatesTab />
      case 'tests':
        return <TestsTab />
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
              ? 'Учётная запись, безопасность и параметры панели'
              : 'Тема интерфейса и смена пароля'}
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
