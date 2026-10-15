export const ROLES = { ADMIN: 'admin', DOCTOR: 'doctor', RECEPTIONIST: 'receptionist', PATIENT: 'patient' }

export const ROLE_HOME = { admin: '/admin', doctor: '/doctor', receptionist: '/reception', patient: '/patient' }

// Where patient records live for each role (patients see their own/family profiles)
export const PATIENT_BASE = {
  admin: '/admin/patients',
  doctor: '/doctor/patients',
  receptionist: '/reception/patients',
  patient: '/patient/profiles',
}

export const APPOINTMENT_BASE = {
  admin: '/admin/appointments',
  doctor: '/doctor/appointments',
  receptionist: '/reception/appointments',
  patient: '/patient/appointments',
}

// Pre-visit history (voicebot) review: clinical roles only
export const HISTORY_BASE = { admin: '/admin/history', doctor: '/doctor/history' }

// Front-desk roles: register walk-ins, check patients in, review possible duplicates
export const FRONT_DESK = [ROLES.ADMIN, ROLES.RECEPTIONIST]

// Sidebar links per role. Add an entry here when a feature page is added.
export const ROLE_NAV = {
  admin: [
    { to: '/admin', label: 'Dashboard', end: true },
    { to: '/admin/queue', label: 'Live queue' },
    { to: '/admin/appointments', label: 'Appointments' },
    { to: '/admin/patients', label: 'Patients' },
    { to: '/admin/doctors', label: 'Doctors' },
    { to: '/admin/holidays', label: 'Holidays' },
  ],
  doctor: [
    { to: '/doctor', label: 'Dashboard', end: true },
    { to: '/doctor/queue', label: 'My queue' },
    { to: '/doctor/appointments', label: 'Appointments' },
    { to: '/doctor/patients', label: 'Patients' },
    { to: '/doctor/schedule', label: 'My schedule' },
  ],
  receptionist: [
    { to: '/reception', label: 'Dashboard', end: true },
    { to: '/reception/queue', label: 'Live queue' },
    { to: '/reception/appointments', label: 'Appointments' },
    { to: '/reception/patients', label: 'Patients' },
  ],
  patient: [
    { to: '/patient', label: 'My profiles', end: true },
    { to: '/patient/appointments', label: 'Appointments' },
  ],
}
