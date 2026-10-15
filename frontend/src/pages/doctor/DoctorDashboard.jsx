import { Link } from 'react-router-dom'
import { updateStatus } from '../../api/appointments'
import PatientRow from '../../components/dashboard/PatientRow'
import StatTiles from '../../components/dashboard/StatTiles'
import useToday from '../../components/dashboard/useToday'
import { cardClass, formatDay, primaryButton, todayISO } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { APPOINTMENT_BASE, HISTORY_BASE } from '../../routes/roles'

const base = APPOINTMENT_BASE.doctor
const ORDER = ['in_consultation', 'with_voicebot', 'waiting']

export default function DoctorDashboard() {
  const { user } = useAuth()
  const { queue, expected, counts, loaded, reload } = useToday()

  // Red flags first, then whoever is with the doctor, then by token
  const active = queue
    .filter((a) => ORDER.includes(a.status))
    .sort((a, b) => b.red_flag - a.red_flag || ORDER.indexOf(a.status) - ORDER.indexOf(b.status) || a.token - b.token)
  const current = active.find((a) => a.status === 'in_consultation')
  const next = active.find((a) => a.status === 'waiting')
  const historiesToReview = queue.filter((a) => a.history_status === 'submitted' && a.status !== 'completed')

  const callIn = async (appt) => {
    await updateStatus(appt.id, 'in_consultation')
    reload()
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-slate-800">Good day, {user.full_name}</h1>
        <p className="text-sm text-slate-500">{formatDay(todayISO())}</p>
      </div>

      <StatTiles
        tiles={[
          { label: 'Waiting', value: counts.waiting, to: '/doctor/queue' },
          { label: 'In consultation', value: counts.in_consultation, to: '/doctor/queue' },
          { label: 'Seen today', value: counts.completed, to: '/doctor/queue' },
          { label: 'Booked, not arrived', value: counts.expected, to: '/doctor/appointments' },
        ]}
      />

      {(current || next) && (
        <section className="rounded-xl bg-brand-gradient p-5 text-white shadow-sm">
          {current ? (
            <p>
              With you now: <b>#{current.token} {current.patient_name}</b>.{' '}
              <Link to={`${base}/${current.id}`} className="underline">
                Open visit
              </Link>
            </p>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p>
                Next: <b>#{next.token} {next.patient_name}</b>
                {next.red_flag && ' (red flag)'}
              </p>
              <button
                className="rounded-md bg-white px-4 py-2 text-sm font-medium text-brand-700 hover:bg-brand-50"
                onClick={() => callIn(next)}
              >
                Call in
              </button>
            </div>
          )}
        </section>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        <section className={`${cardClass} p-0! lg:col-span-2`}>
          <h2 className="border-b border-slate-100 px-4 py-3 text-sm font-semibold text-slate-800">My queue</h2>
          {active.length === 0 ? (
            <p className="p-6 text-center text-sm text-slate-500">{loaded ? 'No one is waiting.' : 'Loading...'}</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {active.map((a) => (
                <PatientRow key={a.id} appt={a} base={base} />
              ))}
            </ul>
          )}
        </section>

        <div className="space-y-5">
          <section className={cardClass}>
            <h2 className="mb-2 text-sm font-semibold text-slate-800">Histories to review</h2>
            {historiesToReview.length === 0 ? (
              <p className="text-sm text-slate-400">None waiting.</p>
            ) : (
              <ul className="space-y-1.5 text-sm">
                {historiesToReview.map((a) => (
                  <li key={a.id}>
                    <Link to={`${HISTORY_BASE.doctor}/${a.history_session_id}`} className="text-brand-700 hover:underline">
                      #{a.token} {a.patient_name}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className={cardClass}>
            <h2 className="mb-2 text-sm font-semibold text-slate-800">Booked, not arrived ({expected.length})</h2>
            {expected.length === 0 ? (
              <p className="text-sm text-slate-400">Everyone booked today has arrived.</p>
            ) : (
              <ul className="space-y-1.5 text-sm text-slate-700">
                {expected.map((a) => (
                  <li key={a.id}>
                    <span className="font-mono text-slate-500">{a.start_time}</span> {a.patient_name}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <Link to="/doctor/schedule" className={`${primaryButton} block text-center`}>
            My schedule and leave
          </Link>
        </div>
      </div>
    </div>
  )
}
