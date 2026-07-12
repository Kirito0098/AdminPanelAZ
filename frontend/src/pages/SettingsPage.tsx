import { FormEvent, useEffect, useMemo, useState } from 'react'
import { Settings, User } from 'lucide-react'
import { Navigate, useParams } from 'react-router-dom'
import { ApiError, changePassword, createUser, deleteUser, getSettings, getUsers } from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import HaReplicaBanner from '@/components/dashboard/HaReplicaBanner'
import MobileSettingsSectionPicker from '@/components/settings/MobileSettingsSectionPicker'
import PageSectionHeader from '@/components/shared/PageSectionHeader'
import BackupTab from '@/components/settings/BackupTab'
import ConfigDeliveryTab from '@/components/settings/ConfigDeliveryTab'
import FeatureTogglesTab from '@/components/settings/FeatureTogglesTab'
import MaintenanceTab from '@/components/settings/MaintenanceTab'
import MonitoringTab from '@/components/settings/MonitoringTab'
import PersonalTab from '@/components/settings/PersonalTab'
import SecurityTab from '@/components/settings/SecurityTab'
import {
  getDefaultSection,
  isSectionAvailable,
  isValidSettingsSection,
  type SettingsSection,
} from '@/components/settings/SettingsNav'
import { getSectionMeta } from '@/components/settings/settingsLabels'
import PanelOpsTab from '@/components/settings/PanelOpsTab'
import RunbookTab from '@/components/settings/RunbookTab'
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

export default function SettingsPage() {
  const { section: sectionParam } = useParams<{ section?: string }>()
  const { user } = useAuth()
  const { isSettingsTabEnabled, isEnabled } = useFeatureModules()
  const { activeNode } = useNode()
  const { theme, setTheme } = useTheme()
  const { success, error: notifyError } = useNotifications()
  const { startGlobal, doneGlobal } = useProgress()
  const { confirm, dialogProps } = useConfirmDialog()
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [users, setUsers] = useState<User[]>([])
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newRole, setNewRole] = useState<UserRole>('user')
  const [currentPwd, setCurrentPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const isAdmin = user?.role === 'admin'

  const defaultSection = getDefaultSection(isAdmin)

  const activeSection = useMemo((): SettingsSection | null => {
    if (!sectionParam) return null
    if (!isValidSettingsSection(sectionParam)) return null
    if (!isSectionAvailable(sectionParam, isAdmin, isSettingsTabEnabled, isEnabled)) return null
    return sectionParam
  }, [sectionParam, isAdmin, isSettingsTabEnabled, isEnabled])

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

  if (!activeSection) {
    return <Navigate to={`/settings/${defaultSection}`} replace />
  }

  const sectionMeta = getSectionMeta(activeSection)

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
      case 'modules':
        return <FeatureTogglesTab />
      case 'updates':
        return <UpdatesTab />
      case 'panel_ops':
        return <PanelOpsTab />
      case 'tests':
        return <RunbookTab />
      case 'vpn_network':
        return <VpnNetworkTab />
      default:
        return null
    }
  }

  return (
    <div className="flex flex-col gap-6 orientation-compact-settings-page">
      <ConfirmDialogHost dialogProps={dialogProps} />
      <HaReplicaBanner />
      <PageSectionHeader
        icon={isAdmin ? Settings : User}
        title={isAdmin ? 'Настройки' : 'Мой профиль'}
        titleAddon={<NodeBadge name={activeNode?.name ?? settings?.node_name} status={activeNode?.status} />}
        description={
          isAdmin
            ? 'Настройте профиль, доступ, VPN и работу панели — разделы в боковом меню «Система»'
            : 'Тема, пароль, Telegram и дополнительная защита при входе'
        }
      />

      <MobileSettingsSectionPicker value={activeSection} />

      <div className="flex flex-col gap-4 orientation-compact-settings-section">
        <div className="rounded-lg border bg-muted/30 px-4 py-3 orientation-compact-settings-section-header">
          <h3 className="text-lg font-semibold tracking-tight">{sectionMeta.title}</h3>
          <p className="text-sm text-muted-foreground">{sectionMeta.description}</p>
          {sectionMeta.hint && (
            <p className="mt-2 text-sm text-muted-foreground/90">{sectionMeta.hint}</p>
          )}
        </div>
        {renderSection()}
      </div>
    </div>
  )
}
