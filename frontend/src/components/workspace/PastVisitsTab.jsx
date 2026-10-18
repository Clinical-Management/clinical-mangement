import { useEffect, useState } from 'react'
import { getPastVisits } from '../../api/workspace'
import { VisitTypeBadge } from '../appointments/Badges'
import { cardClass, formatDate } from '../ui'

const OUTCOME_LABEL = {
  resolved: 'Resolved',
  improving: 'Improving',
  unchanged: 'Unchanged',
  worse: 'Worse',
  referred: 'Referred',
  admitted: 'Admitted',
}

function Detail({ label, children }) {
  if (!children || (Array.isArray(children) && !children.length)) return null
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-0.5 whitespace-pre-line text-sm text-slate-800">{children}</dd>
    </div>
  )
}

export default function PastVisitsTab({ appt }) {
  const [visits, setVisits] = useState(null)
  const [open, setOpen] = useState(null)

  useEffect(() => {
    getPastVisits(appt.patient_id, appt.id).then((v) => {
      setVisits(v)
      setOpen(v[0]?.appointment_id ?? null) // most recent open by default
    })
  }, [appt.patient_id, appt.id])

  if (!visits) return <p className="text-slate-500">Loading...</p>
  if (!visits.length) return <p className={`${cardClass} text-sm text-slate-400`}>No earlier completed visits.</p>

  return (
    <ol className="space-y-3">
      {visits.map((v) => {
        const expanded = open === v.appointment_id
        return (
          <li key={v.appointment_id} className={cardClass}>
            <button className="flex w-full flex-wrap items-center justify-between gap-2 text-left" onClick={() => setOpen(expanded ? null : v.appointment_id)}>
              <span>
                <b className="text-slate-800">{formatDate(v.date)}</b>
                <span className="ml-2 text-sm text-slate-500">{v.doctor_name}</span>
                <span className="ml-2">
                  <VisitTypeBadge type={v.visit_type} />
                </span>
              </span>
              <span className="text-sm text-slate-600">
                {v.diagnoses.map((d) => d.title).join('; ') || v.chief_complaint || 'No diagnosis recorded'}
                {v.outcome && <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs">{OUTCOME_LABEL[v.outcome.status]}</span>}
              </span>
            </button>
            {expanded && (
              <dl className="mt-4 grid gap-4 border-t border-slate-100 pt-4 md:grid-cols-2">
                <Detail label="Chief complaint">{v.chief_complaint}</Detail>
                <Detail label="Diagnosis">
                  {v.diagnoses.map((d) => `${d.code} ${d.title} (${d.status})`).join('\n')}
                </Detail>
                <Detail label="Examination">{v.examination}</Detail>
                <Detail label="Medicines">
                  {v.medicines.map((m) => [m.name, m.dose, m.frequency, m.duration].filter(Boolean).join(' ')).join('\n')}
                </Detail>
                <Detail label="Investigations">{v.investigations.map((i) => i.name).join(', ')}</Detail>
                <Detail label="Advice">{v.advice}</Detail>
                <Detail label="Follow-up">
                  {v.follow_up && [v.follow_up.date && formatDate(v.follow_up.date), v.follow_up.note].filter(Boolean).join(' - ')}
                </Detail>
                <Detail label="Outcome">{v.outcome && `${OUTCOME_LABEL[v.outcome.status]}${v.outcome.note ? `: ${v.outcome.note}` : ''}`}</Detail>
              </dl>
            )}
          </li>
        )
      })}
    </ol>
  )
}
