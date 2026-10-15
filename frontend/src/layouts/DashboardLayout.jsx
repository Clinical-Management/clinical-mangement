import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import Logo from '../components/Logo'
import { useAuth } from '../context/AuthContext'
import { ROLE_NAV } from '../routes/roles'

export default function DashboardLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="hidden w-60 flex-col bg-brand-gradient-vertical md:flex">
        <div className="px-5 py-5">
          <Logo light />
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {ROLE_NAV[user.role].map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `block rounded-md px-3 py-2 text-sm font-medium ${
                  isActive ? 'bg-white/20 text-white shadow-sm' : 'text-white/75 hover:bg-white/10 hover:text-white'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex flex-1 flex-col">
        {/* thin brand strip so the gradient is present on small screens without the sidebar */}
        <div className="h-1 bg-brand-gradient" />
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
          <span className="text-sm font-medium capitalize text-brand-700">{user.role} portal</span>
          <div className="flex items-center gap-4">
            <span className="text-sm font-medium text-slate-700">{user.full_name}</span>
            <button onClick={handleLogout} className="text-sm text-brand-600 hover:underline">
              Log out
            </button>
          </div>
        </header>
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
