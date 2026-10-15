import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import DashboardLayout from './layouts/DashboardLayout'
import AdminDashboard from './pages/admin/AdminDashboard'
import AppointmentDetailPage from './pages/appointments/AppointmentDetailPage'
import AppointmentListPage from './pages/appointments/AppointmentListPage'
import BookAppointmentPage from './pages/appointments/BookAppointmentPage'
import QueuePage from './pages/appointments/QueuePage'
import Login from './pages/auth/Login'
import Register from './pages/auth/Register'
import DoctorDashboard from './pages/doctor/DoctorDashboard'
import NotFound from './pages/NotFound'
import PatientDashboard from './pages/patient/PatientDashboard'
import EditPatientPage from './pages/patients/EditPatientPage'
import PatientDetailPage from './pages/patients/PatientDetailPage'
import PatientListPage from './pages/patients/PatientListPage'
import RegisterPatientPage from './pages/patients/RegisterPatientPage'
import ReceptionistDashboard from './pages/receptionist/ReceptionistDashboard'
import DoctorSchedulePage from './pages/scheduling/DoctorSchedulePage'
import DoctorsPage from './pages/scheduling/DoctorsPage'
import HolidaysPage from './pages/scheduling/HolidaysPage'
import ProtectedRoute from './routes/ProtectedRoute'
import { ROLE_HOME, ROLES } from './routes/roles'

function HomeRedirect() {
  const { user, loading } = useAuth()
  if (loading) return null
  return <Navigate to={user ? ROLE_HOME[user.role] : '/login'} replace />
}

// Patient record pages for staff roles
function patientRoutes(path, { canRegister = true, canEdit = true } = {}) {
  return [
    <Route key="list" path={path} element={<PatientListPage />} />,
    canRegister && <Route key="new" path={`${path}/new`} element={<RegisterPatientPage />} />,
    <Route key="detail" path={`${path}/:patientId`} element={<PatientDetailPage />} />,
    canEdit && <Route key="edit" path={`${path}/:patientId/edit`} element={<EditPatientPage />} />,
  ]
}

function appointmentRoutes({ canBook = true } = {}) {
  return [
    <Route key="appts" path="appointments" element={<AppointmentListPage />} />,
    canBook && <Route key="book" path="appointments/new" element={<BookAppointmentPage />} />,
    <Route key="appt" path="appointments/:appointmentId" element={<AppointmentDetailPage />} />,
  ]
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      <Route element={<ProtectedRoute roles={[ROLES.ADMIN]} />}>
        <Route path="/admin" element={<DashboardLayout />}>
          <Route index element={<AdminDashboard />} />
          {patientRoutes('patients')}
          {appointmentRoutes()}
          <Route path="queue" element={<QueuePage />} />
          <Route path="doctors" element={<DoctorsPage />} />
          <Route path="doctors/:doctorId" element={<DoctorSchedulePage />} />
          <Route path="holidays" element={<HolidaysPage />} />
        </Route>
      </Route>

      <Route element={<ProtectedRoute roles={[ROLES.DOCTOR]} />}>
        <Route path="/doctor" element={<DashboardLayout />}>
          <Route index element={<DoctorDashboard />} />
          {patientRoutes('patients', { canRegister: false, canEdit: false })}
          {appointmentRoutes({ canBook: false })}
          <Route path="queue" element={<QueuePage />} />
          <Route path="schedule" element={<DoctorSchedulePage />} />
        </Route>
      </Route>

      <Route element={<ProtectedRoute roles={[ROLES.RECEPTIONIST]} />}>
        <Route path="/reception" element={<DashboardLayout />}>
          <Route index element={<ReceptionistDashboard />} />
          {patientRoutes('patients')}
          {appointmentRoutes()}
          <Route path="queue" element={<QueuePage />} />
        </Route>
      </Route>

      <Route element={<ProtectedRoute roles={[ROLES.PATIENT]} />}>
        <Route path="/patient" element={<DashboardLayout />}>
          <Route index element={<PatientDashboard />} />
          <Route path="profiles/new" element={<RegisterPatientPage />} />
          <Route path="profiles/:patientId" element={<PatientDetailPage />} />
          <Route path="profiles/:patientId/edit" element={<EditPatientPage />} />
          {appointmentRoutes()}
        </Route>
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
