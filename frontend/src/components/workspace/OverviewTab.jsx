import { useEffect, useState } from 'react'
import { getHistory } from '../../api/history'
import { listReports } from '../../api/reports'
import { VisitTypeBadge } from '../appointments/Badges'
import VitalsPanel from '../clinical/VitalsPanel'
import { BLOOD_GROUPS, GENDERS, labelOf } from '../patients/options'
import { cardClass, formatDate } from '../ui'

function Item({ label, children }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="text-sm text-slate-800">{children || '-'}</dd>
    </div>
  )
}

function ListBlock({ title, items, empty, render, danger }) {
  return (
    <div>
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      {items.length === 0 ? (
        <p className="text-sm text-slate-400">{empty}</p>
      ) : (
        <ul className="space-y-1">
          {items.map((x, i) => (
            <li key={i} className={`rounded-md px-2.5 py-1.5 text-sm ${danger ? 'bg-red-50 text-red-800' : 'bg-slate-50 text-slate-800'}`}>
              {render(x)}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Everything the doctor needs at a glance before starting. */
export default function OverviewTab({ appt, patient }) {
  const [history, setHistory] = useState(null)
  const [criticalLabs, setCriticalLabs] = useState([])
  const medical = patient.medical ?? { allergies: [], chronic_conditions: [], current_medications: [] }

  useEffect(() => {
    if (appt.history_session_id) getHistory(appt.history_session_id).then(setHistory).catch(() => {})
    listReports(patient.patient_id, { include_summary: true })
      .then((reports) =>
        setCriticalLabs(reports.flatMap((r) => (r.summary?.critical_values ?? []).map((v) => `${v} (${formatDate(r.report_date)})`))),
      )
      .catch(() => {})
  }, [appt.history_session_id, patient.patient_id])

  const redFlags = [
    ...(appt.red_flag ? [`Voicebot red flag: ${appt.red_flag_labels}`] : []),
    ...(appt.vitals_flag === 'critical' ? ['Critical vitals at check-in (see below)'] : []),
    ...criticalLabs.map((v) => `Critical lab value: ${v}`),
  ]
  const complaint = history?.fields.find((f) => f.key === 'chief_complaint')?.value

  return (
    <div className="space-y-5">
      {redFlags.length > 0 && (
        <section className="rounded-xl border border-red-300 bg-red-50 p-4">
          <h2 className="mb-1 text-sm font-semibold text-red-800">!! Red flags</h2>
          <ul className="list-inside list-disc text-sm text-red-800">
            {redFlags.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </section>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        <section className={`${cardClass} lg:col-span-2`}>
          <h2 className="mb-3 text-sm font-semibold text-slate-800">This visit</h2>
          <dl className="grid gap-4 sm:grid-cols-3">
            <Item label="Visit type">
              <VisitTypeBadge type={appt.visit_type} overridden={!!appt.visit_type_override} />
              {appt.visit_type_override && <span className="ml-1 text-xs text-slate-500">({appt.visit_type_override.reason})</span>}
            </Item>
            <Item label="Date">
              {formatDate(appt.date)} {appt.start_time ?? '(walk-in)'}
            </Item>
            <Item label="Token">{appt.token && `#${appt.token}`}</Item>
            <div className="sm:col-span-3">
              <Item label="Chief complaint (pre-visit history)">{complaint ?? (appt.history_status ? 'History not submitted yet' : 'No pre-visit history')}</Item>
            </div>
            {history?.summary && (
              <div className="sm:col-span-3">
                <Item label="History summary">
                  <span className="whitespace-pre-line">{history.summary}</span>
                </Item>
              </div>
            )}
          </dl>
        </section>

        <section className={cardClass}>
          <h2 className="mb-3 text-sm font-semibold text-slate-800">Patient</h2>
          <dl className="grid grid-cols-2 gap-3">
            <Item label="Age / sex">
              {patient.age ?? '?'} y / {labelOf(GENDERS, patient.gender)}
            </Item>
            <Item label="Blood group">{labelOf(BLOOD_GROUPS, patient.blood_group)}</Item>
            <Item label="Phone">{patient.phone}</Item>
            <Item label="Patient ID">{patient.patient_id}</Item>
            <div className="col-span-2">
              <Item label="Emergency contact">
                {patient.emergency_contact && `${patient.emergency_contact.name} (${patient.emergency_contact.relationship}) ${patient.emergency_contact.phone}`}
              </Item>
            </div>
          </dl>
        </section>
      </div>

      <section className={`${cardClass} grid gap-5 md:grid-cols-3`}>
        <ListBlock
          title="Allergies"
          items={medical.allergies}
          empty="No known allergies"
          danger
          render={(a) => (
            <>
              <b>{a.substance}</b>
              {a.reaction && ` - ${a.reaction}`}
              {a.severity && ` (${a.severity})`}
            </>
          )}
        />
        <ListBlock
          title="Chronic conditions"
          items={medical.chronic_conditions}
          empty="None recorded"
          render={(c) => (
            <>
              {c.name}
              {c.since_year && <span className="text-slate-500"> since {c.since_year}</span>}
            </>
          )}
        />
        <ListBlock
          title="Current medicines"
          items={medical.current_medications}
          empty="None recorded"
          render={(m) => [m.name, m.dosage, m.frequency].filter(Boolean).join(' ')}
        />
      </section>

      <VitalsPanel appt={appt} canRecord={!['cancelled', 'no_show'].includes(appt.status)} />
    </div>
  )
}
