import { Link } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { APPOINTMENT_BASE } from '../../routes/roles'
import { formatDay } from '../ui'

/** Booked appointments that fall on a newly blocked day (leave / holiday) and need rescheduling. */
export default function ConflictList({ appointments, onClose }) {
  const { user } = useAuth()
  if (!appointments?.length) return null
  const base = APPOINTMENT_BASE[user.role]

  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
      <div className="flex items-start justify-between gap-3">
        <p className="font-semibold">
          {appointments.length} booked appointment{appointments.length > 1 && 's'} fall on the blocked days and need
          rescheduling:
        </p>
        <button className="text-amber-700 hover:underline" onClick={onClose}>
          Dismiss
        </button>
      </div>
      <ul className="mt-2 space-y-1">
        {appointments.map((a) => (
          <li key={a.id}>
            {formatDay(a.date)} {a.start_time} | {a.patient_name} with {a.doctor_name}
            {base && (
              <Link to={`${base}/${a.id}`} className="ml-2 text-brand-700 hover:underline">
                Open
              </Link>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
