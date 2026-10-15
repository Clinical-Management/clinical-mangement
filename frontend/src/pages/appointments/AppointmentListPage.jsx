import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { listAppointments } from '../../api/appointments'
import { StatusBadge, VisitTypeBadge } from '../../components/appointments/Badges'
import DoctorSelect from '../../components/appointments/DoctorSelect'
import { STATUSES } from '../../components/appointments/options'
import { cardClass, errorBox, errorMessage, formatDay, inputClass, primaryButton, todayISO } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { APPOINTMENT_BASE, FRONT_DESK, ROLES } from '../../routes/roles'

const RANGES = [
  { value: 'upcoming', label: 'Upcoming' },
  { value: 'day', label: 'On a date' },
  { value: 'all', label: 'All (newest first)' },
]

export default function AppointmentListPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const base = APPOINTMENT_BASE[user.role]
  const isFrontDesk = FRONT_DESK.includes(user.role)
  const canBook = user.role !== ROLES.DOCTOR

  const [range, setRange] = useState('upcoming')
  const [date, setDate] = useState(todayISO())
  const [doctorId, setDoctorId] = useState('')
  const [status, setStatus] = useState('')
  const [appointments, setAppointments] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const params = {
      date: range === 'day' ? date : undefined,
      date_from: range === 'upcoming' ? todayISO() : undefined,
      doctor_id: doctorId || undefined,
      status: status || undefined,
    }
    let cancelled = false
    listAppointments(params)
      .then((list) => {
        if (cancelled) return
        setAppointments(list)
        setError('')
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err, 'Could not load appointments'))
      })
    return () => {
      cancelled = true
    }
  }, [range, date, doctorId, status])

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-slate-800">Appointments</h1>
        {canBook && (
          <Link to={`${base}/new`} className={primaryButton}>
            Book appointment
          </Link>
        )}
      </div>

      <div className="flex flex-wrap gap-3">
        <select className={`${inputClass} w-auto`} value={range} onChange={(e) => setRange(e.target.value)}>
          {RANGES.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
        {range === 'day' && (
          <input type="date" className={`${inputClass} w-auto`} value={date} onChange={(e) => setDate(e.target.value)} />
        )}
        {isFrontDesk && (
          <DoctorSelect value={doctorId} onChange={setDoctorId} allowAll className={`${inputClass} w-56`} />
        )}
        <select className={`${inputClass} w-auto`} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Any status</option>
          {STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </div>

      {error && <p className={errorBox}>{error}</p>}

      <div className={`${cardClass} overflow-x-auto p-0`}>
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">When</th>
              <th className="px-4 py-3">Patient</th>
              <th className="px-4 py-3">Doctor</th>
              <th className="px-4 py-3">Visit</th>
              <th className="px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {appointments?.map((a) => (
              <tr
                key={a.id}
                onClick={() => navigate(`${base}/${a.id}`)}
                className="cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-50"
              >
                <td className="px-4 py-3 text-slate-700">
                  {formatDay(a.date)}
                  <span className="ml-2 font-mono text-slate-500">
                    {a.start_time ?? 'walk-in'}
                    {a.token && ` #${a.token}`}
                  </span>
                </td>
                <td className="px-4 py-3 font-medium text-slate-800">{a.patient_name}</td>
                <td className="px-4 py-3 text-slate-600">{a.doctor_name}</td>
                <td className="px-4 py-3">
                  <VisitTypeBadge type={a.visit_type} overridden={!!a.visit_type_override} />
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={a.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {appointments?.length === 0 && <p className="p-6 text-center text-sm text-slate-500">No appointments</p>}
        {!appointments && !error && <p className="p-6 text-center text-sm text-slate-500">Loading...</p>}
      </div>
    </div>
  )
}
