import { FormEvent, useEffect, useState } from 'react'
import { ApiError, changePassword, createUser, deleteUser, getSettings, getUsers, updateSettings } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import type { AppSettings, User, UserRole } from '../types'

export default function SettingsPage() {
  const { user } = useAuth()
  const { theme, setTheme } = useTheme()
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [users, setUsers] = useState<User[]>([])
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [includeHosts, setIncludeHosts] = useState('')
  const [excludeHosts, setExcludeHosts] = useState('')
  const [includeIps, setIncludeIps] = useState('')
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newRole, setNewRole] = useState<UserRole>('user')
  const [currentPwd, setCurrentPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')

  const load = async () => {
    try {
      const s = await getSettings()
      setSettings(s)
      setIncludeHosts(s.include_hosts)
      setExcludeHosts(s.exclude_hosts)
      setIncludeIps(s.include_ips)
      if (user?.role === 'admin') {
        setUsers(await getUsers())
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
    }
  }

  useEffect(() => { load() }, [user?.role])

  const saveAntizapret = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    try {
      await updateSettings({ include_hosts: includeHosts, exclude_hosts: excludeHosts, include_ips: includeIps })
      setSuccess('Списки AntiZapret обновлены и применены')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    }
  }

  const handleCreateUser = async (e: FormEvent) => {
    e.preventDefault()
    try {
      await createUser({ username: newUsername, password: newPassword, role: newRole })
      setNewUsername('')
      setNewPassword('')
      setUsers(await getUsers())
      setSuccess('Пользователь создан')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка создания пользователя')
    }
  }

  const handleDeleteUser = async (id: number, name: string) => {
    if (!confirm(`Удалить пользователя "${name}"?`)) return
    try {
      await deleteUser(id)
      setUsers(await getUsers())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка удаления')
    }
  }

  const handleChangePassword = async (e: FormEvent) => {
    e.preventDefault()
    try {
      await changePassword(currentPwd, newPwd)
      setCurrentPwd('')
      setNewPwd('')
      setSuccess('Пароль изменён')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка смены пароля')
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h2>Настройки</h2>
          <p>Тема, пользователи и списки AntiZapret</p>
        </div>
      </header>

      {error && <div className="alert error">{error}</div>}
      {success && <div className="alert success">{success}</div>}

      <section className="card">
        <h3>Внешний вид</h3>
        <div className="theme-switch">
          <button className={`btn ${theme === 'light' ? 'primary' : 'secondary'}`} onClick={() => setTheme('light')}>Светлая</button>
          <button className={`btn ${theme === 'dark' ? 'primary' : 'secondary'}`} onClick={() => setTheme('dark')}>Тёмная</button>
        </div>
        {settings && <p className="muted">Путь AntiZapret: {settings.antizapret_path}</p>}
      </section>

      <section className="card">
        <h3>Смена пароля</h3>
        <form className="form-grid" onSubmit={handleChangePassword}>
          <label>
            Текущий пароль
            <input type="password" value={currentPwd} onChange={(e) => setCurrentPwd(e.target.value)} required />
          </label>
          <label>
            Новый пароль
            <input type="password" value={newPwd} onChange={(e) => setNewPwd(e.target.value)} required minLength={4} />
          </label>
          <button className="btn primary">Сохранить пароль</button>
        </form>
      </section>

      {user?.role === 'admin' && (
        <>
          <section className="card">
            <h3>Списки AntiZapret</h3>
            <form onSubmit={saveAntizapret}>
              <label>
                Включить домены (include-hosts.txt)
                <textarea rows={6} value={includeHosts} onChange={(e) => setIncludeHosts(e.target.value)} />
              </label>
              <label>
                Исключить домены (exclude-hosts.txt)
                <textarea rows={6} value={excludeHosts} onChange={(e) => setExcludeHosts(e.target.value)} />
              </label>
              <label>
                Включить IP (include-ips.txt)
                <textarea rows={4} value={includeIps} onChange={(e) => setIncludeIps(e.target.value)} />
              </label>
              <button className="btn primary">Сохранить и применить (doall.sh)</button>
            </form>
          </section>

          <section className="card">
            <h3>Управление пользователями</h3>
            <form className="form-grid user-form" onSubmit={handleCreateUser}>
              <label>
                Логин
                <input value={newUsername} onChange={(e) => setNewUsername(e.target.value)} required />
              </label>
              <label>
                Пароль
                <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required />
              </label>
              <label>
                Роль
                <select value={newRole} onChange={(e) => setNewRole(e.target.value as UserRole)}>
                  <option value="user">Пользователь</option>
                  <option value="admin">Администратор</option>
                </select>
              </label>
              <button className="btn primary">Добавить</button>
            </form>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>ID</th><th>Логин</th><th>Роль</th><th>Статус</th><th></th></tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id}>
                      <td>{u.id}</td>
                      <td>{u.username}</td>
                      <td>{u.role === 'admin' ? 'Администратор' : 'Пользователь'}</td>
                      <td>{u.is_active ? 'Активен' : 'Отключён'}</td>
                      <td>
                        {u.id !== user?.id && (
                          <button className="btn danger-outline small" onClick={() => handleDeleteUser(u.id, u.username)}>Удалить</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
