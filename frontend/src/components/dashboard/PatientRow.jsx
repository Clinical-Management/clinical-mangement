import { Link } from 'react-router-dom'
import { StatusBadge, VisitTypeBadge } from '../appointments/Badges'

const VITALS_BADGE = {
  critical: { text: '!! Critical vitals', className: 'bg-red-100 text-red-700' },
  abnormal: { text: '▲ Abnormal vitals', className: 'bg-amber-100 text-amber-800' },
}

/** One patient in a dashboard list, with the signals a doctor or front desk needs at a glance. */
export default function PatientRow({ appt, base, children }) {
  const vitals = VITALS_BADGE[appt.vitals_flag]
  return (
    <li className={`flex flex-wrap items-center justify-between gap-2 px-4 py-3 ${appt.red_flag ? 'bg-red-50' : ''}`}>
      <div className="flex min-w-0 items-center gap-3">
        <span className="w-10 shrink-0 text-lg font-semibold text-slate-800">
          {appt.token ? `#${appt.token}` : <span className="font-mono text-sm text-slate-500">{appt.start_time}</span>}
        </span>
        <div className="min-w-0">
          <Link to={`${base}/${appt.id}`} className="font-medium text-slate-800 hover:underline">
            {appt.patient_name}
          </Link>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs">
            <VisitTypeBadge type={appt.visit_type} overridden={!!appt.visit_type_override} />
            {appt.red_flag && (
              <span className="rounded bg-red-600 px-1.5 py-0.5 font-medium text-white">Red flag: {appt.red_flag_labels}</span>
            )}
            {vitals && <span className={`rounded px-1.5 py-0.5 ${vitals.className}`}>{vitals.text}</span>}
            {appt.history_status === 'submitted' && (
              <span className="rounded bg-accent-50 px-1.5 py-0.5 text-accent-700">History ready</span>
            )}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <StatusBadge status={appt.status} />
        {children}
      </div>
    </li>
  )
}
