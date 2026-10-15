import { Link } from 'react-router-dom'
import { checkIn } from '../../api/appointments'
import { useAuth } from '../../context/AuthContext'
import { APPOINTMENT_BASE, PATIENT_BASE } from '../../routes/roles'
import { cardClass, formatDay, primaryButton, todayISO } from '../ui'
import PatientRow from './PatientRow'
import StatTiles from './StatTiles'
import useToday from './useToday'

/** Shared by reception and admin: today's numbers, arrivals to check in, and quick actions. */
export default function FrontDeskDashboard({ title, extraActions = [] }) {
  const { user } = useAuth()
  const { queue, expected, counts, loaded, reload } = useToday()
  const appts = APPOINTMENT_BASE[user.role]
  const patients = PATIENT_BASE[user.role]
  const queuePath = appts.replace('appointments', 'queue')

  const flagged = queue.filter((a) => (a.red_flag || a.vitals_flag === 'critical') && a.status !== 'completed')

  const actions = [
    { to: `${appts}/new`, label: 'Book appointment' },
    { to: `${appts}/new?mode=walk-in`, label: 'Add walk-in' },
    { to: `${patients}/new`, label: 'Register patient' },
    { to: patients, label: 'Find patient' },
    ...extraActions,
  ]

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">{title}</h1>
          <p className="text-sm text-slate-500">{formatDay(todayISO())}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {actions.map((a, i) => (
            <Link key={a.to} to={a.to} className={i === 0 ? primaryButton : 'rounded-md border border-brand-200 bg-white px-4 py-2 text-sm font-medium text-brand-700 hover:bg-brand-50'}>
              {a.label}
            </Link>
          ))}
        </div>
      </div>

      <StatTiles
        tiles={[
          { label: 'Booked, not arrived', value: counts.expected, to: queuePath },
          { label: 'Waiting', value: counts.waiting, to: queuePath },
          { label: 'In consultation', value: counts.in_consultation, to: queuePath },
          { label: 'Completed', value: counts.completed, to: queuePath },
        ]}
      />

      {flagged.length > 0 && (
        <section className="rounded-xl border border-red-300 bg-red-50 p-0">
          <h2 className="px-4 py-3 text-sm font-semibold text-red-800">Needs attention</h2>
          <ul className="divide-y divide-red-100">
            {flagged.map((a) => (
              <PatientRow key={a.id} appt={a} base={appts} />
            ))}
          </ul>
        </section>
      )}

      <section className={`${cardClass} p-0!`}>
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-800">Arrivals to check in</h2>
          <Link to={queuePath} className="text-sm text-brand-600 hover:underline">
            Open live queue
          </Link>
        </div>
        {expected.length === 0 ? (
          <p className="p-6 text-center text-sm text-slate-500">{loaded ? 'Everyone booked today has arrived.' : 'Loading...'}</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {expected.map((a) => (
              <PatientRow key={a.id} appt={a} base={appts}>
                <span className="hidden text-xs text-slate-500 sm:inline">{a.doctor_name}</span>
                <button
                  className={`${primaryButton} px-3 py-1 text-xs`}
                  onClick={() => checkIn(a.id).then(reload)}
                >
                  Check in
                </button>
              </PatientRow>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
