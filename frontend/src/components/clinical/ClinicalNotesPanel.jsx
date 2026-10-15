import { useEffect, useRef, useState } from 'react'
import { addDiagnosis, getNotes, removeDiagnosis, saveExamination, searchIcd10, updateDiagnosis } from '../../api/clinical'
import { useSpeechInput } from '../../hooks/useSpeech'
import { cardClass, errorMessage, formatDate, formatTime, inputClass, primaryButton } from '../ui'

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

/** Doctor's examination findings (typed or dictated) and ICD-10 diagnoses for one visit. */
export default function ClinicalNotesPanel({ appt }) {
  const [notes, setNotes] = useState(null)
  const [draft, setDraft] = useState('')
  const [dictated, setDictated] = useState(false)
  const [status, setStatus] = useState('provisional')
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(true)

  const speech = useSpeechInput('en', (text) => {
    setDraft((d) => (d ? `${d.trimEnd()} ${text}` : text))
    setDictated(true)
    setSaved(false)
  })

  useEffect(() => {
    getNotes(appt.id).then((n) => {
      setNotes(n)
      setDraft(n.examination)
    })
  }, [appt.id])

  const run = async (action) => {
    setError('')
    try {
      setNotes(await action())
      return true
    } catch (err) {
      setError(errorMessage(err, 'Could not save'))
      return false
    }
  }

  if (!notes) return null

  return (
    <section className={`${cardClass} space-y-5`}>
      <div>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-800">Examination findings</h2>
          {speech.supported && (
            <button
              type="button"
              onClick={speech.listening ? speech.stop : speech.start}
              className={`rounded-md px-3 py-1.5 text-sm font-medium ${speech.listening ? 'animate-pulse bg-red-600 text-white' : 'border border-brand-200 text-brand-700 hover:bg-brand-50'}`}
            >
              {speech.listening ? 'Stop dictation' : 'Dictate'}
            </button>
          )}
        </div>
        <textarea
          className={inputClass}
          rows={6}
          placeholder="General examination, systemic examination..."
          value={draft + (speech.interim ? ` ${speech.interim}` : '')}
          onChange={(e) => {
            setDraft(e.target.value)
            setSaved(false)
          }}
        />
        {speech.error && <p className="mt-1 text-xs text-amber-700">Dictation unavailable ({speech.error}); please type.</p>}
        <div className="mt-2 flex items-center justify-between">
          <span className="text-xs text-slate-400">
            {notes.examination_updated_at
              ? `Saved ${formatDate(notes.examination_updated_at)} ${formatTime(notes.examination_updated_at)}`
              : 'Not saved yet'}
          </span>
          <button
            className={primaryButton}
            disabled={saved}
            onClick={() => run(() => saveExamination(appt.id, draft, dictated)).then((ok) => ok && setSaved(true))}
          >
            Save findings
          </button>
        </div>
      </div>

      <div>
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
                    onClick={() =>
                      run(() => updateDiagnosis(appt.id, d.id, { status: d.status === 'final' ? 'provisional' : 'final' }))
                    }
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
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {notes.changes.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-xs text-slate-500">Change log ({notes.changes.length})</summary>
          <ul className="mt-2 space-y-1 text-xs text-slate-600">
            {notes.changes.map((c, i) => (
              <li key={i}>
                {formatDate(c.at)} {formatTime(c.at)} - {c.change} ({c.by_role})
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="text-xs text-slate-400">ICD-10-CM FY2026 code set.</p>
    </section>
  )
}
