import { Link } from 'react-router-dom'
import { cardClass } from '../../components/ui'
import { APPOINTMENT_BASE, PATIENT_BASE } from '../../routes/roles'

const patients = PATIENT_BASE.receptionist
const appointments = APPOINTMENT_BASE.receptionist

const ACTIONS = [
  { to: '/reception/queue', title: 'Live queue', text: "Check in today's appointments and move patients along." },
  { to: `${appointments}/new`, title: 'Book appointment', text: 'Find a free slot with any doctor.' },
  { to: `${appointments}/new?mode=walk-in`, title: 'Add walk-in', text: "Put a patient straight into today's queue." },
  { to: patients, title: 'Find a patient', text: 'Scan the patient QR code or search by ID, name or phone.' },
  { to: `${patients}/new`, title: 'Register new patient', text: 'Create a patient record and capture consent.' },
]

export default function ReceptionistDashboard() {
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold text-slate-800">Reception</h1>
      <div className="grid gap-4 sm:grid-cols-2">
        {ACTIONS.map((a) => (
          <Link key={a.to} to={a.to} className={`${cardClass} transition hover:border-accent-600`}>
            <h2 className="font-semibold text-brand-700">{a.title}</h2>
            <p className="mt-1 text-sm text-slate-500">{a.text}</p>
          </Link>
        ))}
      </div>
    </div>
  )
}
