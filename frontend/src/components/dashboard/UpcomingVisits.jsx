import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listAppointments } from '../../api/appointments'
import { APPOINTMENT_BASE } from '../../routes/roles'
import { StatusBadge } from '../appointments/Badges'
import { cardClass, formatDay, primaryButton, todayISO } from '../ui'

const base = APPOINTMENT_BASE.patient
const ACTIVE = ['scheduled', 'waiting', 'with_voicebot', 'in_consultation']

/** Patient home: upcoming visits for the whole family, with a shortcut to today's pre-visit history. */
export default function UpcomingVisits() {
  const [visits, setVisits] = useState(null)

  useEffect(() => {
    listAppointments({ date_from: todayISO() })
      .then((list) => setVisits(list.filter((a) => ACTIVE.includes(a.status))))
      .catch(() => setVisits([]))
  }, [])

  if (!visits) return null

  return (
    <section className={cardClass}>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-800">Upcoming visits</h2>
        <Link to={`${base}/new`} className="text-sm text-brand-600 hover:underline">
          Book a visit
        </Link>
      </div>
      {visits.length === 0 ? (
        <p className="text-sm text-slate-400">No upcoming visits.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {visits.map((a) => {
            const today = a.date === todayISO()
            const historyDue = today && !['submitted', 'escalated'].includes(a.history_status)
            return (
              <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
                <Link to={`${base}/${a.id}`} className="hover:underline">
                  <b>{formatDay(a.date)}</b> {a.start_time ?? ''} | {a.patient_name} with {a.doctor_name}
                  {a.token && <span className="ml-1 text-slate-500">(token #{a.token})</span>}
                </Link>
                <span className="flex items-center gap-2">
                  <StatusBadge status={a.status} />
                  {historyDue && (
                    <Link to={`${base}/${a.id}`} className={`${primaryButton} px-3 py-1 text-xs`}>
                      Tell us your symptoms
                    </Link>
                  )}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
