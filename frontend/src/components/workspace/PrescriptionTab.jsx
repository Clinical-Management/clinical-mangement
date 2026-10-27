import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getCaseSummary } from '../../api/caseSummary'
import { patchNotes } from '../../api/clinical'
import {
  addFavourite,
  deleteFavourite,
  finalizePrescription,
  listFavourites,
  listTemplates,
  saveTemplate,
} from '../../api/prescriptions'
import { getFollowUp } from '../../api/reminders'
import { getPrescription, savePrescription } from '../../api/workspace'
import { useAuth } from '../../context/AuthContext'
import useAutosave from '../../hooks/useAutosave'
import { APPOINTMENT_BASE } from '../../routes/roles'
import ChecksPanel from '../prescriptions/ChecksPanel'
import MedicineSearch from '../prescriptions/MedicineSearch'
import PrescriptionVersions from '../prescriptions/PrescriptionVersions'
import { cardClass, errorMessage, formatDate, inputClass, labelClass, primaryButton, secondaryButton } from '../ui'
import SaveIndicator from './SaveIndicator'

const MED_FIELDS = [
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
const MED_KEYS = ['name', 'medicine_id', 'generic', 'brand', 'dose', 'frequency', 'duration', 'route', 'instructions']

const blankMed = () => Object.fromEntries(MED_KEYS.map((k) => [k, '']))
const clean = (v) => (v?.trim?.() ? v.trim() : null)
const cleanMed = (m) => Object.fromEntries(MED_KEYS.map((k) => [k, k === 'name' ? m.name.trim() : clean(m[k])]))

// Only complete rows are saved; empty drafts stay on screen until filled in
function toPayload(rx) {
  const fu = rx.follow_up
  return {
    medicines: rx.medicines.filter((m) => m.name.trim()).map(cleanMed),
    investigations: rx.investigations.filter((i) => i.name.trim()).map((i) => ({ name: i.name.trim(), notes: clean(i.notes) })),
    advice: rx.advice,
    diet_lifestyle: rx.diet_lifestyle,
    referral: rx.referral.to.trim() ? { to: rx.referral.to.trim(), specialty: clean(rx.referral.specialty), notes: clean(rx.referral.notes) } : null,
    follow_up:
      fu.in_days !== '' || fu.date || fu.note.trim()
        ? { in_days: fu.in_days === '' ? null : Number(fu.in_days), date: fu.in_days === '' ? fu.date || null : null, note: clean(fu.note) }
        : null,
    summary_sections: rx.summary_sections,
  }
}

function fromServer(p) {
  return {
    medicines: p.medicines.map((m) => ({ ...blankMed(), ...Object.fromEntries(Object.entries(m).map(([k, v]) => [k, v ?? ''])) })),
    investigations: p.investigations.map((i) => ({ name: i.name, notes: i.notes ?? '' })),
    advice: p.advice ?? '',
    diet_lifestyle: p.diet_lifestyle ?? '',
    referral: { to: p.referral?.to ?? '', specialty: p.referral?.specialty ?? '', notes: p.referral?.notes ?? '' },
    follow_up: { in_days: p.follow_up?.in_days ?? '', date: p.follow_up?.in_days == null ? (p.follow_up?.date ?? '') : '', note: p.follow_up?.note ?? '' },
    summary_sections: p.summary_sections ?? {},
  }
}

function FinalizePanel({ server, onFinalize, onCancel }) {
  const warnings = server.checks.filter((c) => c.severity !== 'info')
  const serious = warnings.some((c) => c.severity === 'high')
  const [ack, setAck] = useState(false)
  const [reason, setReason] = useState('')
  const ready = !warnings.length || (ack && (!serious || reason.trim().length >= 3))

  return (
    <section className="rounded-xl border-2 border-brand-200 bg-white p-4">
      <h2 className="mb-2 text-sm font-semibold text-slate-800">Finalize version {server.editing_version}</h2>
      {warnings.length > 0 ? (
        <>
          <ChecksPanel checks={warnings} />
          <label className="mt-3 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />I have reviewed these warnings
          </label>
          {serious && (
            <input
              className={`${inputClass} mt-2`}
              placeholder="Reason for prescribing despite serious warnings (recorded)"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          )}
        </>
      ) : (
        <p className="text-sm text-slate-600">No warnings. The finalized version is signed and gets a verification QR code.</p>
      )}
      <div className="mt-3 flex justify-end gap-2">
        <button className={secondaryButton} onClick={onCancel}>
          Cancel
        </button>
        <button className={primaryButton} disabled={!ready} onClick={() => onFinalize({ acknowledged: ack || !warnings.length, override_reason: reason.trim() || null })}>
          Finalize and sign
        </button>
      </div>
    </section>
  )
}

export default function PrescriptionTab({ appt, notes, onNotesSaved, active = true }) {
  const { user } = useAuth()
  const [rx, setRx] = useState(null)
  const [server, setServer] = useState(null) // last saved: checks, status, follow-up date
  const [caseSummary, setCaseSummary] = useState(undefined)
  const [favourites, setFavourites] = useState([])
  const [templates, setTemplates] = useState([])
  const [finalizing, setFinalizing] = useState(false)
  const [versionsKey, setVersionsKey] = useState(0)
  const [followUp, setFollowUp] = useState(null) // booked automatically when finalized
  const [error, setError] = useState('')
  const [outcome, setOutcome] = useState({ status: notes.outcome?.status ?? '', note: notes.outcome?.note ?? '' })

  const save = useCallback(async (draft) => setServer(await savePrescription(appt.id, toPayload(draft))), [appt.id])
  const autosave = useAutosave(rx, save, { enabled: rx !== null })
  const saveOutcome = useCallback(
    async (o) => o.status && onNotesSaved(await patchNotes(appt.id, { outcome: { status: o.status, note: clean(o.note) } })),
    [appt.id, onNotesSaved],
  )
  const outcomeSave = useAutosave(outcome, saveOutcome)
  const { reset, flush } = autosave

  useEffect(() => {
    if (active) getCaseSummary(appt.id).then(setCaseSummary).catch(() => setCaseSummary(null))
  }, [appt.id, active])

  useEffect(() => {
    getFollowUp(appt.id).then(setFollowUp).catch(() => {})
  }, [appt.id, versionsKey])

  useEffect(() => {
    getPrescription(appt.id).then((p) => {
      const draft = fromServer(p)
      reset(draft)
      setRx(draft)
      setServer(p)
    })
    listFavourites().then(setFavourites).catch(() => {})
    listTemplates().then(setTemplates).catch(() => {})
  }, [appt.id, reset])

  if (!rx || !server) return <p className="text-slate-500">Loading...</p>

  const setMed = (i, patch) => setRx({ ...rx, medicines: rx.medicines.map((m, j) => (j === i ? { ...m, ...patch } : m)) })
  const addMeds = (meds) => setRx({ ...rx, medicines: [...rx.medicines.filter((m) => m.name.trim()), ...meds.map((m) => ({ ...blankMed(), ...m }))] })
  const setInv = (i, key, value) => setRx({ ...rx, investigations: rx.investigations.map((m, j) => (j === i ? { ...m, [key]: value } : m)) })

  const applyTemplate = (id) => {
    const t = templates.find((x) => x.id === id)
    if (!t) return
    const asStrings = (m) => Object.fromEntries(Object.entries(m).map(([k, v]) => [k, v ?? '']))
    setRx({
      ...rx,
      medicines: [...rx.medicines.filter((m) => m.name.trim()), ...t.medicines.map((m) => ({ ...blankMed(), ...asStrings(m) }))],
      investigations: [...rx.investigations.filter((i) => i.name.trim()), ...t.investigations.map((i) => ({ name: i.name, notes: i.notes ?? '' }))],
      advice: [rx.advice, t.advice].filter(Boolean).join('\n'),
      diet_lifestyle: [rx.diet_lifestyle, t.diet_lifestyle].filter(Boolean).join('\n'),
    })
  }

  const saveAsTemplate = async () => {
    const name = window.prompt('Template name, e.g. "Viral fever - adult"')
    if (!name?.trim()) return
    const p = toPayload(rx)
    const t = await saveTemplate({ name: name.trim(), medicines: p.medicines, investigations: p.investigations, advice: p.advice, diet_lifestyle: p.diet_lifestyle })
    setTemplates([...templates, t])
  }

  const doFinalize = async (body) => {
    setError('')
    try {
      await flush()
      await finalizePrescription(appt.id, body)
      const p = await getPrescription(appt.id)
      setServer(p)
      setFinalizing(false)
      setVersionsKey((k) => k + 1)
    } catch (err) {
      setError(errorMessage(err, 'Could not finalize'))
    }
  }

  const final = server.status === 'final'
  const favouriteNames = new Set(favourites.map((f) => f.medicine.name))

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-600">
          <span className={`mr-2 rounded-full px-2 py-0.5 text-xs font-medium ${final ? 'bg-accent-100 text-accent-700' : 'bg-amber-100 text-amber-800'}`}>
            {final ? `Finalized v${server.current_version}` : `Draft of v${server.editing_version}`}
          </span>
          {final ? 'Editing will start a new version; this one stays viewable.' : 'Saved automatically.'}
        </p>
        <div className="flex items-center gap-2">
          <SaveIndicator autosave={autosave} />
          {!final && !finalizing && (
            <button className={primaryButton} onClick={() => flush().then(() => setFinalizing(true))}>
              Finalize...
            </button>
          )}
        </div>
      </div>
      {finalizing && <FinalizePanel server={server} onFinalize={doFinalize} onCancel={() => setFinalizing(false)} />}
      {error && <p className="text-sm text-red-600">{error}</p>}

      <section className={cardClass}>
        <h2 className="mb-2 text-sm font-semibold text-slate-800">Safety checks</h2>
        <ChecksPanel checks={server.checks} />
      </section>

      <section className={cardClass}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-800">Medicines</h2>
          <div className="flex flex-wrap items-center gap-2">
            {templates.length > 0 && (
              <select className={`${inputClass} w-auto! py-1.5`} value="" onChange={(e) => applyTemplate(e.target.value)} aria-label="Apply template">
                <option value="">Apply template...</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            )}
            <button className="text-sm text-brand-600 hover:underline" onClick={saveAsTemplate}>
              Save as template
            </button>
          </div>
        </div>

        {favourites.length > 0 && (
          <div className="mb-3 flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-slate-500">Favourites:</span>
            {favourites.map((f) => (
              <span key={f.id} className="inline-flex items-center rounded-full border border-brand-200 text-xs">
                <button className="px-2 py-1 text-brand-700 hover:bg-brand-50" onClick={() => addMeds([f.medicine])}>
                  + {f.medicine.name} {f.medicine.dose}
                </button>
                <button className="pr-2 text-slate-400 hover:text-red-600" title="Remove favourite" onClick={() => deleteFavourite(f.id).then(() => setFavourites(favourites.filter((x) => x.id !== f.id)))}>
                  x
                </button>
              </span>
            ))}
          </div>
        )}

        <div className="space-y-2">
          {rx.medicines.map((m, i) => (
            <div key={i} className="grid grid-cols-2 gap-2 rounded-md border border-slate-200 p-2 sm:grid-cols-6">
              <label className="col-span-2 sm:col-span-1">
                <span className="text-xs text-slate-500">Medicine *</span>
                <MedicineSearch value={m.name} onChange={(name) => setMed(i, { name, medicine_id: '' })} onPick={(picked) => setMed(i, picked)} />
                {m.generic && m.generic !== m.name && <span className="text-xs text-slate-400">{m.generic}</span>}
              </label>
              {MED_FIELDS.map(([key, label, placeholder]) => (
                <label key={key} className={key === 'instructions' ? 'col-span-2 sm:col-span-1' : ''}>
                  <span className="text-xs text-slate-500">{label}</span>
                  <input className={`${inputClass} py-1.5`} placeholder={placeholder} value={m[key]} onChange={(e) => setMed(i, { [key]: e.target.value })} />
                </label>
              ))}
              <div className="col-span-2 flex justify-end gap-3 text-xs sm:col-span-6">
                {m.name.trim() && !favouriteNames.has(m.name.trim()) && (
                  <button className="text-brand-600 hover:underline" onClick={() => addFavourite(cleanMed(m)).then((f) => setFavourites([...favourites, f]))}>
                    ★ Save as favourite
                  </button>
                )}
                <button className="text-red-600 hover:underline" onClick={() => setRx({ ...rx, medicines: rx.medicines.filter((_, j) => j !== i) })}>
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
        <button className="mt-2 text-sm text-brand-600 hover:underline" onClick={() => setRx({ ...rx, medicines: [...rx.medicines, blankMed()] })}>
          + Add medicine
        </button>
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className={cardClass}>
          <h2 className="mb-3 text-sm font-semibold text-slate-800">Investigations advised</h2>
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
              <input type="number" min={0} max={365} className={inputClass} value={rx.follow_up.in_days}
                onChange={(e) => setRx({ ...rx, follow_up: { ...rx.follow_up, in_days: e.target.value, date: '' } })} />
            </label>
            <label>
              <span className={labelClass}>Or on date</span>
              <input type="date" className={inputClass} value={rx.follow_up.in_days !== '' ? (server.follow_up?.date ?? '') : rx.follow_up.date}
                onChange={(e) => setRx({ ...rx, follow_up: { ...rx.follow_up, date: e.target.value, in_days: '' } })} />
            </label>
            <label className="col-span-2">
              <span className={labelClass}>Note</span>
              <input className={inputClass} placeholder="e.g. Review with reports" value={rx.follow_up.note} onChange={(e) => setRx({ ...rx, follow_up: { ...rx.follow_up, note: e.target.value } })} />
            </label>
          </div>
          {followUp && followUp.status === 'scheduled' ? (
            <p className="mt-2 rounded-md bg-accent-50 px-3 py-2 text-sm text-accent-700">
              Follow-up booked for {formatDate(followUp.date)} at {followUp.start_time}.{' '}
              <Link to={`${APPOINTMENT_BASE[user.role]}/${followUp.id}`} className="underline">
                Open
              </Link>
            </p>
          ) : (
            server.follow_up?.date && (
              <p className="mt-2 text-xs text-slate-500">
                Finalizing books the nearest free slot on or after {formatDate(server.follow_up.date)} and reminds the patient.
              </p>
            )
          )}
        </section>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className={cardClass}>
          <h2 className="mb-2 text-sm font-semibold text-slate-800">Advice</h2>
          <textarea className={inputClass} rows={4} placeholder="Warning signs to return early, precautions..." value={rx.advice} onChange={(e) => setRx({ ...rx, advice: e.target.value })} />
        </section>
        <section className={cardClass}>
          <h2 className="mb-2 text-sm font-semibold text-slate-800">Diet and lifestyle</h2>
          <textarea className={inputClass} rows={4} placeholder="Diet, activity, sleep, smoking/alcohol..." value={rx.diet_lifestyle} onChange={(e) => setRx({ ...rx, diet_lifestyle: e.target.value })} />
        </section>
      </div>

      <section className={cardClass}>
        <h2 className="mb-3 text-sm font-semibold text-slate-800">Referral</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <input className={inputClass} placeholder="Refer to (doctor / hospital)" value={rx.referral.to} onChange={(e) => setRx({ ...rx, referral: { ...rx.referral, to: e.target.value } })} />
          <input className={inputClass} placeholder="Specialty, e.g. ENT" value={rx.referral.specialty} onChange={(e) => setRx({ ...rx, referral: { ...rx.referral, specialty: e.target.value } })} />
          <input className={inputClass} placeholder="Referral notes" value={rx.referral.notes} onChange={(e) => setRx({ ...rx, referral: { ...rx.referral, notes: e.target.value } })} />
        </div>
      </section>

      <section className={cardClass}>
        <h2 className="mb-2 text-sm font-semibold text-slate-800">Case summary in the prescription</h2>
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
            {caseSummary === undefined ? 'Loading...' : 'Finalize the case summary (Case summary tab) to include it in the prescription PDF.'}
          </p>
        )}
      </section>

      <PrescriptionVersions appt={appt} refreshKey={versionsKey} />

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
