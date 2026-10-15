import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { checkIn, getQueue, listAppointments, updateStatus } from '../../api/appointments'
import { StatusBadge, VisitTypeBadge } from '../../components/appointments/Badges'
import DoctorSelect from '../../components/appointments/DoctorSelect'
import { NEXT_ACTIONS, STATUS_META } from '../../components/appointments/options'
import { cardClass, errorBox, errorMessage, formatDay, inputClass, primaryButton, secondaryButton, todayISO } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { APPOINTMENT_BASE, FRONT_DESK, ROLES } from '../../routes/roles'

const POLL_MS = 5000
const ACTIVE = ['in_consultation', 'with_voicebot', 'waiting']

function QueueRow({ appt, base, onAction }) {
  return (
    <tr className={`border-b border-slate-100 last:border-0 ${appt.red_flag ? 'bg-red-50' : ''}`}>
      <td className="px-4 py-3 text-lg font-semibold text-slate-800">#{appt.token}</td>
      <td className="px-4 py-3">
        <Link to={`${base}/${appt.id}`} className="font-medium text-slate-800 hover:underline">
          {appt.patient_name}
        </Link>
        <span className="block text-xs text-slate-500">
          {appt.start_time ? `Slot ${appt.start_time}` : 'Walk-in'} | {appt.doctor_name}
          {appt.history_status === 'submitted' && ' | history ready'}
        </span>
        {appt.red_flag && (
          <span className="mt-1 inline-block rounded bg-red-600 px-1.5 py-0.5 text-xs font-medium text-white">
            Red flag: {appt.red_flag_labels}
          </span>
        )}
      </td>
      <td className="px-4 py-3">
        <VisitTypeBadge type={appt.visit_type} overridden={!!appt.visit_type_override} />
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={appt.status} />
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap justify-end gap-2">
          {(NEXT_ACTIONS[appt.status] ?? []).map((a) => (
            <button
              key={a.to}
              className={`${a.subtle ? secondaryButton : primaryButton} px-3 py-1 text-xs`}
              onClick={() => onAction(() => updateStatus(appt.id, a.to))}
            >
              {a.label}
            </button>
          ))}
        </div>
      </td>
    </tr>
  )
}

export default function QueuePage() {
  const { user } = useAuth()
  const base = APPOINTMENT_BASE[user.role]
  const isFrontDesk = FRONT_DESK.includes(user.role)
  const isDoctor = user.role === ROLES.DOCTOR

  const [doctorId, setDoctorId] = useState('')
  const [queue, setQueue] = useState([])
  const [expected, setExpected] = useState([]) // booked for today, not yet arrived
  const [error, setError] = useState('')
  const [updatedAt, setUpdatedAt] = useState(null)

  const load = useCallback(async () => {
    const today = todayISO()
    const doctor = isDoctor ? undefined : doctorId || undefined
    try {
      const [q, e] = await Promise.all([
        getQueue({ date: today, doctor_id: doctor }),
        isFrontDesk ? listAppointments({ date: today, status: 'scheduled', doctor_id: doctor }) : [],
      ])
      setQueue(q)
      setExpected(e)
      setUpdatedAt(new Date())
      setError('')
    } catch (err) {
      setError(errorMessage(err, 'Could not load the queue'))
    }
  }, [doctorId, isDoctor, isFrontDesk])

  // Live updates by polling; pauses while the tab is hidden
  useEffect(() => {
    const tick = () => document.visibilityState === 'visible' && load()
    tick()
    const timer = setInterval(tick, POLL_MS)
    document.addEventListener('visibilitychange', tick)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [load])

  const act = async (action) => {
    try {
      await action()
      await load()
    } catch (err) {
      setError(errorMessage(err, 'Action failed'))
    }
  }

  const active = queue.filter((a) => ACTIVE.includes(a.status))
  // Consultation first, then voicebot, then waiting; tokens ascending within each
  active.sort((a, b) => ACTIVE.indexOf(a.status) - ACTIVE.indexOf(b.status) || a.token - b.token)
  const completed = queue.filter((a) => a.status === 'completed')
  const counts = Object.fromEntries(ACTIVE.concat('completed').map((s) => [s, queue.filter((a) => a.status === s).length]))

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">Live queue</h1>
          <p className="text-sm text-slate-500">
            {formatDay(todayISO())} | updates every {POLL_MS / 1000}s
            {updatedAt && ` | last ${updatedAt.toLocaleTimeString()}`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {!isDoctor && <DoctorSelect value={doctorId} onChange={setDoctorId} allowAll className={`${inputClass} w-56`} />}
          {isFrontDesk && (
            <Link to={`${base}/new?mode=walk-in`} className={primaryButton}>
              Add walk-in
            </Link>
          )}
        </div>
      </div>

      {error && <p className={errorBox}>{error}</p>}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Object.entries(counts).map(([status, n]) => (
          <div key={status} className={`${cardClass} p-4`}>
            <p className="text-2xl font-semibold text-slate-800">{n}</p>
            <p className="text-xs text-slate-500">{STATUS_META[status].label}</p>
          </div>
        ))}
      </div>

      <section className={`${cardClass} overflow-x-auto p-0`}>
        <table className="w-full text-left text-sm">
          <tbody>
            {active.map((a) => (
              <QueueRow key={a.id} appt={a} base={base} onAction={act} />
            ))}
          </tbody>
        </table>
        {active.length === 0 && <p className="p-6 text-center text-sm text-slate-500">No one is waiting.</p>}
      </section>

      {isFrontDesk && expected.length > 0 && (
        <section className={cardClass}>
          <h2 className="mb-3 text-sm font-semibold text-slate-800">Expected today, not checked in ({expected.length})</h2>
          <ul className="divide-y divide-slate-100">
            {expected.map((a) => (
              <li key={a.id} className="flex items-center justify-between py-2 text-sm">
                <span>
                  <span className="font-mono text-slate-500">{a.start_time}</span>{' '}
                  <Link to={`${base}/${a.id}`} className="font-medium text-slate-800 hover:underline">
                    {a.patient_name}
                  </Link>
                  <span className="ml-2 text-slate-500">{a.doctor_name}</span>
                </span>
                <button className={`${primaryButton} px-3 py-1 text-xs`} onClick={() => act(() => checkIn(a.id))}>
                  Check in
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {completed.length > 0 && (
        <details className={cardClass}>
          <summary className="cursor-pointer text-sm font-semibold text-slate-800">Completed ({completed.length})</summary>
          <ul className="mt-3 space-y-1 text-sm text-slate-600">
            {completed.map((a) => (
              <li key={a.id}>
                #{a.token} {a.patient_name} <span className="text-slate-400">| {a.doctor_name}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}
