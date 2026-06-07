import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'

const navItems = [
  { to: '/', label: 'Конфигурации', icon: '⚙️' },
  { to: '/monitoring', label: 'Мониторинг', icon: '📊' },
  { to: '/settings', label: 'Настройки', icon: '🔧' },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">🛡️</div>
          <div>
            <h1>AntiZapret</h1>
            <p>VPN Панель</p>
          </div>
        </div>
        <nav className="nav">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === '/'} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <span>{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <button className="btn ghost" onClick={() => toggleTheme()}>
            {theme === 'dark' ? '☀️ Светлая' : '🌙 Тёмная'}
          </button>
          <div className="user-badge">
            <strong>{user?.username}</strong>
            <span>{user?.role === 'admin' ? 'Администратор' : 'Пользователь'}</span>
          </div>
          <button className="btn danger-outline" onClick={logout}>Выйти</button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
