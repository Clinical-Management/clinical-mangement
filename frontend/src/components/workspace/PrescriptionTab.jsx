import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { patchNotes } from '../../api/clinical'
import { getCaseSummary } from '../../api/caseSummary'
import { getPrescription, savePrescription } from '../../api/workspace'
import { useAuth } from '../../context/AuthContext'
import useAutosave from '../../hooks/useAutosave'
import { APPOINTMENT_BASE, WORKSPACE_BASE } from '../../routes/roles'
import { cardClass, formatDate, inputClass, labelClass } from '../ui'
import SaveIndicator from './SaveIndicator'

const MED_FIELDS = [
  ['name', 'Medicine *', 'e.g. Paracetamol'],
  ['dose', 'Dose', '500 mg'],
  ['frequency', 'Frequency', '1-0-1'],
  ['duration', 'Duration', '5 days'],
  ['route', 'Route', 'oral'],
  ['instructions', 'Instructions', 'after food'],
]
const OUTCOMES = [
  ['', 'Not recorded'],
  ['resolved', 'Resolved'],
  ['improving', 'Improving'],
  ['unchanged', 'Unchanged'],
  ['worse', 'Worse'],
  ['referred', 'Referred'],
  ['admitted', 'Admitted'],
]

const blankMed = () => ({ name: '', dose: '', frequency: '', duration: '', route: '', instructions: '' })
const clean = (v) => (v?.trim?.() ? v.trim() : null)

// Only complete rows are saved; empty drafts stay on screen until filled in
function toPayload(rx) {
  return {
    medicines: rx.medicines
      .filter((m) => m.name.trim())
      .map((m) => Object.fromEntries(Object.entries(m).map(([k, v]) => [k, k === 'name' ? v.trim() : clean(v)]))),
    investigations: rx.investigations.filter((i) => i.name.trim()).map((i) => ({ name: i.name.trim(), notes: clean(i.notes) })),
    advice: rx.advice,
    follow_up:
      rx.follow_up.in_days !== '' || rx.follow_up.note.trim()
        ? { in_days: rx.follow_up.in_days === '' ? null : Number(rx.follow_up.in_days), note: clean(rx.follow_up.note) }
        : null,
    summary_sections: rx.summary_sections,
  }
}

function fromServer(p) {
  return {
    medicines: p.medicines.map((m) => ({ ...blankMed(), ...Object.fromEntries(Object.entries(m).map(([k, v]) => [k, v ?? ''])) })),
    investigations: p.investigations.map((i) => ({ name: i.name, notes: i.notes ?? '' })),
    advice: p.advice ?? '',
    follow_up: { in_days: p.follow_up?.in_days ?? '', note: p.follow_up?.note ?? '' },
    summary_sections: p.summary_sections ?? {},
  }
}

export default function PrescriptionTab({ appt, notes, onNotesSaved, active = true }) {
  const { user } = useAuth()
  const [rx, setRx] = useState(null)
  const [server, setServer] = useState(null) // last saved (warnings, follow-up date)
  const [caseSummary, setCaseSummary] = useState(undefined) // undefined = loading, null = none
  const [outcome, setOutcome] = useState({ status: notes.outcome?.status ?? '', note: notes.outcome?.note ?? '' })

  const save = useCallback(async (draft) => setServer(await savePrescription(appt.id, toPayload(draft))), [appt.id])
  const autosave = useAutosave(rx, save, { enabled: rx !== null })
  const saveOutcome = useCallback(
    async (o) => o.status && onNotesSaved(await patchNotes(appt.id, { outcome: { status: o.status, note: clean(o.note) } })),
    [appt.id, onNotesSaved],
  )
  const outcomeSave = useAutosave(outcome, saveOutcome)
  const { reset } = autosave

  // re-checked each time the tab is shown: the summary may have been finalized meanwhile
  useEffect(() => {
    if (active) getCaseSummary(appt.id).then(setCaseSummary).catch(() => setCaseSummary(null))
  }, [appt.id, active])

  useEffect(() => {
    getPrescription(appt.id).then((p) => {
      const draft = fromServer(p)
      reset(draft)
      setRx(draft)
      setServer(p)
    })
  }, [appt.id, reset])

  if (!rx) return <p className="text-slate-500">Loading...</p>

  const setMed = (i, key, value) => setRx({ ...rx, medicines: rx.medicines.map((m, j) => (j === i ? { ...m, [key]: value } : m)) })
  const setInv = (i, key, value) => setRx({ ...rx, investigations: rx.investigations.map((m, j) => (j === i ? { ...m, [key]: value } : m)) })

  return (
    <div className="space-y-5">
      <div className="flex justify-end">
        <SaveIndicator autosave={autosave} />
      </div>

      {server?.allergy_warnings.length > 0 && (
        <section className="rounded-xl border border-red-300 bg-red-50 p-4 text-sm text-red-800">
          <h2 className="mb-1 font-semibold">!! Allergy check</h2>
          <ul className="list-inside list-disc">
            {server.allergy_warnings.map((w, i) => (
              <li key={i}>
                <b>{w.medicine}</b>: patient is allergic to <b>{w.allergy}</b> ({w.reason})
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className={cardClass}>
        <h2 className="mb-3 text-sm font-semibold text-slate-800">Medicines</h2>
        <div className="space-y-2">
          {rx.medicines.map((m, i) => (
            <div key={i} className="grid grid-cols-2 gap-2 rounded-md border border-slate-200 p-2 sm:grid-cols-6">
              {MED_FIELDS.map(([key, label, placeholder]) => (
                <label key={key} className={key === 'name' || key === 'instructions' ? 'col-span-2 sm:col-span-1' : ''}>
                  <span className="text-xs text-slate-500">{label}</span>
                  <input className={`${inputClass} py-1.5`} placeholder={placeholder} value={m[key]} onChange={(e) => setMed(i, key, e.target.value)} />
                </label>
              ))}
              <button
                type="button"
                className="col-span-2 text-right text-xs text-red-600 hover:underline sm:col-span-6"
                onClick={() => setRx({ ...rx, medicines: rx.medicines.filter((_, j) => j !== i) })}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
        <button className="mt-2 text-sm text-brand-600 hover:underline" onClick={() => setRx({ ...rx, medicines: [...rx.medicines, blankMed()] })}>
          + Add medicine
        </button>
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className={cardClass}>
          <h2 className="mb-3 text-sm font-semibold text-slate-800">Investigations</h2>
          <div className="space-y-2">
            {rx.investigations.map((inv, i) => (
              <div key={i} className="flex gap-2">
                <input className={inputClass} placeholder="e.g. CBC, Lipid profile" value={inv.name} onChange={(e) => setInv(i, 'name', e.target.value)} />
                <input className={inputClass} placeholder="Notes" value={inv.notes} onChange={(e) => setInv(i, 'notes', e.target.value)} />
                <button type="button" className="px-1 text-sm text-red-600" title="Remove" onClick={() => setRx({ ...rx, investigations: rx.investigations.filter((_, j) => j !== i) })}>
                  x
                </button>
              </div>
            ))}
          </div>
          <button className="mt-2 text-sm text-brand-600 hover:underline" onClick={() => setRx({ ...rx, investigations: [...rx.investigations, { name: '', notes: '' }] })}>
            + Add investigation
          </button>
        </section>

        <section className={cardClass}>
          <h2 className="mb-3 text-sm font-semibold text-slate-800">Follow-up</h2>
          <div className="grid grid-cols-2 gap-3">
            <label>
              <span className={labelClass}>In (days)</span>
              <input
                type="number"
                min={0}
                max={365}
                className={inputClass}
                value={rx.follow_up.in_days}
                onChange={(e) => setRx({ ...rx, follow_up: { ...rx.follow_up, in_days: e.target.value } })}
              />
            </label>
            <div>
              <span className={labelClass}>Date</span>
              <p className="py-2 text-sm text-slate-700">{server?.follow_up?.date ? formatDate(server.follow_up.date) : '-'}</p>
            </div>
            <label className="col-span-2">
              <span className={labelClass}>Note</span>
              <input className={inputClass} placeholder="e.g. Review with reports" value={rx.follow_up.note} onChange={(e) => setRx({ ...rx, follow_up: { ...rx.follow_up, note: e.target.value } })} />
            </label>
          </div>
          {server?.follow_up?.date && (
            <Link to={`${APPOINTMENT_BASE[user.role]}/new?patient_id=${appt.patient_id}`} className="mt-2 inline-block text-sm text-brand-600 hover:underline">
              Book the follow-up
            </Link>
          )}
        </section>
      </div>

      <section className={cardClass}>
        <h2 className="mb-2 text-sm font-semibold text-slate-800">Advice</h2>
        <textarea className={inputClass} rows={4} placeholder="Diet, activity, warning signs to return early..." value={rx.advice} onChange={(e) => setRx({ ...rx, advice: e.target.value })} />
      </section>

      <section className={cardClass}>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-800">Case summary in the prescription</h2>
          <a href={`${WORKSPACE_BASE[user.role]}/${appt.id}/print`} target="_blank" rel="noreferrer" className="text-sm font-medium text-brand-600 hover:underline">
            Print prescription
          </a>
        </div>
        {caseSummary?.status === 'final' ? (
          <div className="grid gap-2 sm:grid-cols-3">
            {caseSummary.sections.map((s) => (
              <label key={s.key} className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  // plan is off by default: the prescription already lists it
                  checked={rx.summary_sections[s.key] ?? s.key !== 'plan'}
                  onChange={(e) => setRx({ ...rx, summary_sections: { ...rx.summary_sections, [s.key]: e.target.checked } })}
                />
                {s.title}
              </label>
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-500">
            {caseSummary === undefined ? 'Loading...' : 'Finalize the case summary (Case summary tab) to include it in the printed prescription.'}
          </p>
        )}
      </section>

      <section className={cardClass}>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-800">Visit outcome</h2>
          <SaveIndicator autosave={outcomeSave} />
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <select className={inputClass} value={outcome.status} onChange={(e) => setOutcome({ ...outcome, status: e.target.value })}>
            {OUTCOMES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <input className={`${inputClass} sm:col-span-2`} placeholder="Outcome note (shown in Past Visits)" value={outcome.note} onChange={(e) => setOutcome({ ...outcome, note: e.target.value })} />
        </div>
      </section>
    </div>
  )
}
