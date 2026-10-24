import { useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import AlertsBanner from '../components/history/AlertsBanner'
import Logo from '../components/Logo'
import { useAuth } from '../context/AuthContext'
import { ROLE_HOME, ROLE_NAV, ROLES } from '../routes/roles'

function NavLinks({ role, onNavigate }) {
  return ROLE_NAV[role].map((item) => (
    <NavLink
      key={item.to}
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) =>
        `block rounded-md px-3 py-2 text-sm font-medium ${
          isActive ? 'bg-white/20 text-white shadow-sm' : 'text-white/75 hover:bg-white/10 hover:text-white'
        }`
      }
    >
      {item.label}
    </NavLink>
  ))
}

export default function DashboardLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [menuFor, setMenuFor] = useState(null) // the path the phone menu was opened on
  const menuOpen = menuFor === pathname

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="hidden w-60 shrink-0 flex-col bg-brand-gradient-vertical md:flex">
        <div className="px-5 py-5">
          <Logo light />
        </div>
        <nav className="flex-1 space-y-1 px-3">
          <NavLinks role={user.role} />
        </nav>
      </aside>

      {/* phone: slide-over menu */}
      {menuOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button className="absolute inset-0 bg-slate-900/40" aria-label="Close menu" onClick={() => setMenuFor(null)} />
          <nav className="relative h-full w-64 space-y-1 bg-brand-gradient-vertical px-3 py-5">
            <div className="mb-4 px-2">
              <Logo light />
            </div>
            <NavLinks role={user.role} onNavigate={() => setMenuFor(null)} />
          </nav>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* thin brand strip so the gradient is present on small screens without the sidebar */}
        <div className="h-1 bg-brand-gradient" />
        <header className="flex items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <button className="rounded-md p-1.5 text-slate-600 hover:bg-slate-100 md:hidden" aria-label="Open menu" onClick={() => setMenuFor(pathname)}>
              <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" />
              </svg>
            </button>
            <span className="text-sm font-medium capitalize text-brand-700">{user.role} portal</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="hidden text-sm font-medium text-slate-700 sm:inline">{user.full_name}</span>
            {user.role !== ROLES.PATIENT && (
              <Link to={`${ROLE_HOME[user.role]}/security`} className="text-sm text-slate-500 hover:text-brand-700">
                Security
              </Link>
            )}
            <button onClick={handleLogout} className="text-sm text-brand-600 hover:underline">
              Log out
            </button>
          </div>
        </header>
        {user.role !== ROLES.PATIENT && <AlertsBanner />}
        <main className="flex-1 p-4 sm:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
