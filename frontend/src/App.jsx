import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import DashboardLayout from './layouts/DashboardLayout'
import Login from './pages/auth/Login'
import Landing from './pages/Landing'
import Register from './pages/auth/Register'
import NotFound from './pages/NotFound'
import ProtectedRoute from './routes/ProtectedRoute'
import { ROLE_HOME, ROLES } from './routes/roles'

// Pages load on demand so each role downloads only what it uses
const AdminDashboard = lazy(() => import('./pages/admin/AdminDashboard'))
const AppointmentDetailPage = lazy(() => import('./pages/appointments/AppointmentDetailPage'))
const AppointmentListPage = lazy(() => import('./pages/appointments/AppointmentListPage'))
const BookAppointmentPage = lazy(() => import('./pages/appointments/BookAppointmentPage'))
const QueuePage = lazy(() => import('./pages/appointments/QueuePage'))
const DoctorDashboard = lazy(() => import('./pages/doctor/DoctorDashboard'))
const PatientDashboard = lazy(() => import('./pages/patient/PatientDashboard'))
const EditPatientPage = lazy(() => import('./pages/patients/EditPatientPage'))
const PatientDetailPage = lazy(() => import('./pages/patients/PatientDetailPage'))
const PatientListPage = lazy(() => import('./pages/patients/PatientListPage'))
const RegisterPatientPage = lazy(() => import('./pages/patients/RegisterPatientPage'))
const HistoryReviewPage = lazy(() => import('./pages/history/HistoryReviewPage'))
const ReceptionistDashboard = lazy(() => import('./pages/receptionist/ReceptionistDashboard'))
const ReportDetailPage = lazy(() => import('./pages/reports/ReportDetailPage'))
const ReportLibraryPage = lazy(() => import('./pages/reports/ReportLibraryPage'))
const ReportSummaryPage = lazy(() => import('./pages/reports/ReportSummaryPage'))
const UploadReportPage = lazy(() => import('./pages/reports/UploadReportPage'))
const DoctorSchedulePage = lazy(() => import('./pages/scheduling/DoctorSchedulePage'))
const DoctorsPage = lazy(() => import('./pages/scheduling/DoctorsPage'))
const HolidaysPage = lazy(() => import('./pages/scheduling/HolidaysPage'))
const VoicebotPage = lazy(() => import('./pages/voice/VoicebotPage'))
const CaseWorkspacePage = lazy(() => import('./pages/workspace/CaseWorkspacePage'))
const AuditLogPage = lazy(() => import('./pages/admin/AuditLogPage'))
const BillingPage = lazy(() => import('./pages/billing/BillingPage'))
const BillingSettingsPage = lazy(() => import('./pages/billing/BillingSettingsPage'))
const PatientBillsPage = lazy(() => import('./pages/patient/PatientBillsPage'))
const ClinicSettingsPage = lazy(() => import('./pages/admin/ClinicSettingsPage'))
const SecurityPage = lazy(() => import('./pages/account/SecurityPage'))
const StaffPage = lazy(() => import('./pages/admin/StaffPage'))
const PatientPrescriptionPage = lazy(() => import('./pages/public/PatientPrescriptionPage'))
const VerifyPrescriptionPage = lazy(() => import('./pages/public/VerifyPrescriptionPage'))

function HomeRedirect() {
  const { user, loading } = useAuth()
  if (loading) return null
  return user ? <Navigate to={ROLE_HOME[user.role]} replace /> : <Landing />
}

// Patient record pages for staff roles
function patientRoutes(path, { canRegister = true, canEdit = true } = {}) {
  return [
    <Route key="list" path={path} element={<PatientListPage />} />,
    canRegister && <Route key="new" path={`${path}/new`} element={<RegisterPatientPage />} />,
    <Route key="detail" path={`${path}/:patientId`} element={<PatientDetailPage />} />,
    canEdit && <Route key="edit" path={`${path}/:patientId/edit`} element={<EditPatientPage />} />,
    ...reportRoutes(path),
  ]
}

// A patient's report library (all roles; `path` is that role's patient base)
function reportRoutes(path) {
  return [
    <Route key="reports" path={`${path}/:patientId/reports`} element={<ReportLibraryPage />} />,
    <Route key="upload" path={`${path}/:patientId/reports/upload`} element={<UploadReportPage />} />,
    <Route key="report" path={`${path}/:patientId/reports/:reportId`} element={<ReportDetailPage />} />,
    <Route key="summary" path={`${path}/:patientId/reports/:reportId/summary`} element={<ReportSummaryPage />} />,
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
    <Suspense fallback={<div className="grid h-screen place-items-center text-slate-500">Loading...</div>}>
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      {/* Voicebot: full screen, opened with a kiosk/phone link token or by a logged-in patient */}
      <Route path="/voice/:sessionId" element={<VoicebotPage />} />
      {/* Prescriptions without login: QR verification and the patient's delivery link */}
      <Route path="/verify/:publicId" element={<VerifyPrescriptionPage />} />
      <Route path="/rx/:publicId" element={<PatientPrescriptionPage />} />

      <Route element={<ProtectedRoute roles={[ROLES.ADMIN]} />}>
        <Route path="/admin" element={<DashboardLayout />}>
          <Route index element={<AdminDashboard />} />
          {patientRoutes('patients')}
          {appointmentRoutes()}
          <Route path="queue" element={<QueuePage />} />
          <Route path="doctors" element={<DoctorsPage />} />
          <Route path="doctors/:doctorId" element={<DoctorSchedulePage />} />
          <Route path="holidays" element={<HolidaysPage />} />
          <Route path="settings/clinic" element={<ClinicSettingsPage />} />
          <Route path="staff" element={<StaffPage />} />
          <Route path="billing" element={<BillingPage />} />
          <Route path="billing/settings" element={<BillingSettingsPage />} />
          <Route path="audit" element={<AuditLogPage />} />
          <Route path="security" element={<SecurityPage />} />
          <Route path="visits/:appointmentId" element={<CaseWorkspacePage />} />
          <Route path="history/:sessionId" element={<HistoryReviewPage />} />
        </Route>
      </Route>

      <Route element={<ProtectedRoute roles={[ROLES.DOCTOR]} />}>
        <Route path="/doctor" element={<DashboardLayout />}>
          <Route index element={<DoctorDashboard />} />
          {patientRoutes('patients', { canRegister: false, canEdit: false })}
          {appointmentRoutes({ canBook: false })}
          <Route path="queue" element={<QueuePage />} />
          <Route path="schedule" element={<DoctorSchedulePage />} />
          <Route path="security" element={<SecurityPage />} />
          <Route path="visits/:appointmentId" element={<CaseWorkspacePage />} />
          <Route path="history/:sessionId" element={<HistoryReviewPage />} />
        </Route>
      </Route>

      <Route element={<ProtectedRoute roles={[ROLES.RECEPTIONIST]} />}>
        <Route path="/reception" element={<DashboardLayout />}>
          <Route index element={<ReceptionistDashboard />} />
          {patientRoutes('patients')}
          {appointmentRoutes()}
          <Route path="queue" element={<QueuePage />} />
          <Route path="billing" element={<BillingPage />} />
          <Route path="security" element={<SecurityPage />} />
        </Route>
      </Route>

      <Route element={<ProtectedRoute roles={[ROLES.PATIENT]} />}>
        <Route path="/patient" element={<DashboardLayout />}>
          <Route index element={<PatientDashboard />} />
          <Route path="profiles/new" element={<RegisterPatientPage />} />
          <Route path="profiles/:patientId" element={<PatientDetailPage />} />
          <Route path="profiles/:patientId/edit" element={<EditPatientPage />} />
          {reportRoutes('profiles')}
          {appointmentRoutes()}
          <Route path="bills" element={<PatientBillsPage />} />
        </Route>
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
    </Suspense>
  )
}
