import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ROLE_HOME } from './roles'

export default function ProtectedRoute({ roles }) {
  const { user, loading } = useAuth()

  if (loading) return <div className="grid h-screen place-items-center text-slate-500">Loading...</div>
  if (!user) return <Navigate to="/login" replace />
  if (roles && !roles.includes(user.role)) return <Navigate to={ROLE_HOME[user.role]} replace />
  return <Outlet />
}
