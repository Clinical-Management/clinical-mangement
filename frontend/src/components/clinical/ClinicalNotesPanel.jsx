import { useCallback, useRef, useState } from 'react'
import { addDiagnosis, patchNotes, removeDiagnosis, searchIcd10, updateDiagnosis } from '../../api/clinical'
import useAutosave from '../../hooks/useAutosave'
import useVisitNotes from '../../hooks/useVisitNotes'
import { useSpeechInput } from '../../hooks/useSpeech'
import { cardClass, errorMessage, formatDate, formatTime, inputClass } from '../ui'
import SaveIndicator from '../workspace/SaveIndicator'

function Icd10Search({ onPick }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const timer = useRef(null)

  const onChange = (value) => {
    setQ(value)
    clearTimeout(timer.current)
    if (value.trim().length < 2) return setResults([])
    timer.current = setTimeout(() => searchIcd10(value).then(setResults).catch(() => setResults([])), 250)
  }

  return (
    <div className="relative">
      <input
        className={inputClass}
        placeholder="Search ICD-10 by code or words, e.g. E11.9 or type 2 diabetes"
        value={q}
        onChange={(e) => onChange(e.target.value)}
      />
      {results.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-md border border-slate-200 bg-white shadow-lg">
          {results.map((r) => (
            <li key={r.code}>
              <button
                type="button"
                className="w-full px-3 py-2 text-left text-sm hover:bg-brand-50"
                onClick={() => {
                  onPick(r)
                  setQ('')
                  setResults([])
                }}
              >
                <span className="font-mono font-medium text-brand-700">{r.code}</span> {r.title}
                {!r.billable && <span className="ml-1 text-xs text-slate-400">(category)</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Autosaved free text with optional dictation. */
function DictationField({ label, value, onChange, onDictated, rows = 6, placeholder, autosave }) {
  const speech = useSpeechInput('en', (text) => {
    onChange(value ? `${value.trimEnd()} ${text}` : text)
    onDictated?.()
  })
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-800">{label}</h2>
        <span className="flex items-center gap-3">
          <SaveIndicator autosave={autosave} />
          {speech.supported && (
            <button
              type="button"
              onClick={speech.listening ? speech.stop : speech.start}
              className={`rounded-md px-3 py-1.5 text-sm font-medium ${speech.listening ? 'animate-pulse bg-red-600 text-white' : 'border border-brand-200 text-brand-700 hover:bg-brand-50'}`}
            >
              {speech.listening ? 'Stop dictation' : 'Dictate'}
            </button>
          )}
        </span>
      </div>
      <textarea
        className={inputClass}
        rows={rows}
        placeholder={placeholder}
        value={value + (speech.interim ? ` ${speech.interim}` : '')}
        onChange={(e) => onChange(e.target.value)}
      />
      {speech.error && <p className="mt-1 text-xs text-amber-700">Dictation unavailable ({speech.error}); please type.</p>}
    </div>
  )
}

/** Examination findings and the doctor's private notes, both autosaved. */
export function ExaminationEditor({ appt, notes, onSaved }) {
  const [exam, setExam] = useState(notes.examination)
  const [docNotes, setDocNotes] = useState(notes.doctor_notes ?? '')
  const dictated = useRef(false)

  const saveExam = useCallback(
    async (text) => onSaved(await patchNotes(appt.id, { examination: text, dictated: dictated.current })),
    [appt.id, onSaved],
  )
  const saveDocNotes = useCallback(async (text) => onSaved(await patchNotes(appt.id, { doctor_notes: text })), [appt.id, onSaved])
  const examSave = useAutosave(exam, saveExam)
  const notesSave = useAutosave(docNotes, saveDocNotes)

  return (
    <section className={`${cardClass} space-y-5`}>
      <DictationField
        label="Examination findings"
        value={exam}
        onChange={setExam}
        onDictated={() => (dictated.current = true)}
        placeholder="General examination, systemic examination..."
        autosave={examSave}
      />
      <DictationField
        label="Doctor's notes (private)"
        value={docNotes}
        onChange={setDocNotes}
        rows={3}
        placeholder="Working notes; not shared with the patient"
        autosave={notesSave}
      />
    </section>
  )
}

/** Provisional / final diagnoses with ICD-10 search. */
export function DiagnosisEditor({ appt, notes, onSaved }) {
  const [status, setStatus] = useState('provisional')
  const [error, setError] = useState('')

  const run = async (action) => {
    setError('')
    try {
      onSaved(await action())
    } catch (err) {
      setError(errorMessage(err, 'Could not save'))
    }
  }

  return (
    <section className={cardClass}>
      <h2 className="mb-2 text-sm font-semibold text-slate-800">Diagnosis</h2>
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-64 flex-1">
          <Icd10Search onPick={(r) => run(() => addDiagnosis(appt.id, { code: r.code, status }))} />
        </div>
        <select className={`${inputClass} w-auto!`} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="provisional">Add as provisional</option>
          <option value="final">Add as final</option>
        </select>
      </div>

      {notes.diagnoses.length === 0 ? (
        <p className="mt-3 text-sm text-slate-400">No diagnosis recorded.</p>
      ) : (
        <ul className="mt-3 divide-y divide-slate-100 rounded-md border border-slate-200">
          {notes.diagnoses.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
              <span>
                <span className="font-mono font-medium text-brand-700">{d.code}</span> {d.title}
                <span
                  className={`ml-2 rounded px-1.5 py-0.5 text-xs ${d.status === 'final' ? 'bg-accent-100 text-accent-700' : 'bg-slate-100 text-slate-600'}`}
                >
                  {d.status}
                </span>
              </span>
              <span className="flex gap-3">
                <button
                  className="text-xs text-brand-600 hover:underline"
                  onClick={() => run(() => updateDiagnosis(appt.id, d.id, { status: d.status === 'final' ? 'provisional' : 'final' }))}
                >
                  Mark {d.status === 'final' ? 'provisional' : 'final'}
                </button>
                <button className="text-xs text-red-600 hover:underline" onClick={() => run(() => removeDiagnosis(appt.id, d.id))}>
                  Remove
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      <p className="mt-3 text-xs text-slate-400">Saved as soon as you add or change a diagnosis. ICD-10-CM FY2026 code set.</p>
    </section>
  )
}

export function NotesChangeLog({ notes }) {
  if (!notes.changes.length) return null
  return (
    <details className={`${cardClass} text-sm`}>
      <summary className="cursor-pointer text-xs text-slate-500">Change log ({notes.changes.length})</summary>
      <ul className="mt-2 space-y-1 text-xs text-slate-600">
        {notes.changes.map((c, i) => (
          <li key={i}>
            {formatDate(c.at)} {formatTime(c.at)} - {c.change} ({c.by_role})
          </li>
        ))}
      </ul>
    </details>
  )
}

/** Examination + diagnosis for one visit (appointment page). */
export default function ClinicalNotesPanel({ appt }) {
  const [notes, setNotes] = useVisitNotes(appt.id)
  if (!notes) return null
  return (
    <div className="space-y-5">
      <ExaminationEditor appt={appt} notes={notes} onSaved={setNotes} />
      <DiagnosisEditor appt={appt} notes={notes} onSaved={setNotes} />
      <NotesChangeLog notes={notes} />
    </div>
  )
}
