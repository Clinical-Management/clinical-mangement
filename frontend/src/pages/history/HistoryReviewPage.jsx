import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  editHistorySummary,
  getHistory,
  reviewHistoryField,
  saveManualHistory,
  submitManualHistory,
} from '../../api/history'
import {
  cardClass,
  errorBox,
  errorMessage,
  formatDate,
  formatTime,
  inputClass,
  primaryButton,
  secondaryButton,
} from '../../components/ui'

const REVIEW_STYLE = {
  pending: 'bg-slate-100 text-slate-600',
  accepted: 'bg-accent-100 text-accent-700',
  edited: 'bg-brand-100 text-brand-800',
  rejected: 'bg-red-100 text-red-700 line-through',
}

const LANGUAGE = { en: 'English', hi: 'Hindi', mr: 'Marathi' }

const groupBySection = (fields) =>
  fields.reduce((groups, f) => ({ ...groups, [f.section]: [...(groups[f.section] ?? []), f] }), {})

function FieldRow({ field, onAction }) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(field.value)

  return (
    <div className="grid gap-2 border-b border-slate-100 py-3 last:border-0 sm:grid-cols-[180px_1fr_auto]">
      <div className="text-sm font-medium text-slate-700">
        {field.label}
        {field.origin === 'previous' && <span className="block text-xs font-normal text-slate-400">from last visit</span>}
      </div>
      {editing ? (
        <textarea className={inputClass} rows={2} value={value} onChange={(e) => setValue(e.target.value)} />
      ) : (
        <p className={`whitespace-pre-line text-sm ${field.review_status === 'rejected' ? 'text-slate-400 line-through' : 'text-slate-800'}`}>
          {field.value || <span className="text-slate-400">Not captured</span>}
        </p>
      )}
      <div className="flex items-start gap-1.5">
        {field.review_status && (
          <span className={`rounded px-2 py-0.5 text-xs ${REVIEW_STYLE[field.review_status]}`}>{field.review_status}</span>
        )}
        {editing ? (
          <>
            <button className="text-xs text-brand-600 hover:underline" onClick={() => onAction('edit', value).then(() => setEditing(false))}>
              Save
            </button>
            <button className="text-xs text-slate-500 hover:underline" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </>
        ) : (
          field.review_status && (
            <>
              <button className="text-xs text-accent-700 hover:underline" onClick={() => onAction('accept')}>
                Accept
              </button>
              <button className="text-xs text-red-600 hover:underline" onClick={() => onAction('reject')}>
                Reject
              </button>
              <button className="text-xs text-brand-600 hover:underline" onClick={() => setEditing(true)}>
                Edit
              </button>
            </>
          )
        )}
      </div>
    </div>
  )
}

function ManualEntry({ session, onSaved }) {
  const [values, setValues] = useState(() => Object.fromEntries(session.fields.map((f) => [f.key, f.value])))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const save = async (submit) => {
    setSaving(true)
    setError('')
    try {
      let updated = await saveManualHistory(session.id, values)
      if (submit) updated = await submitManualHistory(session.id)
      onSaved(updated)
    } catch (err) {
      setError(errorMessage(err, 'Could not save'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className={`${cardClass} space-y-5`}>
      <p className="text-sm text-slate-500">
        Typing the history for the patient. Fields from their last visit are pre-filled; confirm or update them.
      </p>
      {Object.entries(groupBySection(session.fields)).map(([section, fields]) => (
        <div key={section}>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{section}</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            {fields.map((f) => (
              <label key={f.key} className={f.key === 'chief_complaint' || f.key === 'complaint_details' ? 'sm:col-span-2' : ''}>
                <span className="mb-1 block text-xs font-medium text-slate-600">{f.label}</span>
                <textarea
                  rows={2}
                  className={inputClass}
                  value={values[f.key]}
                  onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
                />
              </label>
            ))}
          </div>
        </div>
      ))}
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex justify-end gap-2">
        <button className={secondaryButton} disabled={saving} onClick={() => save(false)}>
          Save draft
        </button>
        <button className={primaryButton} disabled={saving || !values.chief_complaint?.trim()} onClick={() => save(true)}>
          Submit history
        </button>
      </div>
    </section>
  )
}

export default function HistoryReviewPage() {
  const { sessionId } = useParams()
  return <HistoryWorkspace sessionId={sessionId} />
}

/** A voicebot history: summary, editable structured fields, collapsible transcript and log. */
export function HistoryWorkspace({ sessionId, embedded = false }) {
  const [session, setSession] = useState(null)
  const [error, setError] = useState('')
  const [summary, setSummary] = useState(null) // editing draft
  const [manual, setManual] = useState(false)

  useEffect(() => {
    getHistory(sessionId)
      .then(setSession)
      .catch((err) => setError(errorMessage(err, 'Could not load history')))
  }, [sessionId])

  const act = async (action) => {
    setError('')
    try {
      setSession(await action())
    } catch (err) {
      setError(errorMessage(err, 'Action failed'))
    }
  }

  if (!session) return error ? <p className={errorBox}>{error}</p> : <p className="text-slate-500">Loading...</p>

  const submitted = session.status === 'submitted'
  const pending = session.fields.filter((f) => f.review_status === 'pending').length
  const showManual = !submitted && session.status !== 'escalated' && (manual || session.mode === 'manual')

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          {embedded ? (
            <h2 className="text-lg font-semibold text-slate-800">Pre-visit history</h2>
          ) : (
            <h1 className="text-2xl font-semibold text-slate-800">History: {session.patient_name}</h1>
          )}
          <p className="text-sm text-slate-500">
            {session.patient_id} | {session.template.replace('_', ' ')} | {LANGUAGE[session.language]} |{' '}
            {session.mode === 'manual' ? 'entered by staff' : `${session.mode} with assistant`}
            {session.returning && ' | returning patient'}
            {session.submitted_at && ` | submitted ${formatDate(session.submitted_at)} ${formatTime(session.submitted_at)}`}
          </p>
        </div>
        {!submitted && !showManual && session.status !== 'escalated' && (
          <button className={secondaryButton} onClick={() => setManual(true)}>
            Take over: enter manually
          </button>
        )}
      </div>

      {error && <p className={errorBox}>{error}</p>}

      {session.red_flags.length > 0 && (
        <section className="rounded-xl border border-red-300 bg-red-50 p-4 text-sm text-red-800">
          <h2 className="mb-1 font-semibold">Red flags</h2>
          <ul className="space-y-1">
            {session.red_flags.map((r, i) => (
              <li key={i}>
                <b>{r.label}</b> ({r.source === 'rules' ? 'keyword rule' : 'assistant'}): "{r.evidence}"
              </li>
            ))}
          </ul>
        </section>
      )}

      {!submitted && !showManual && (
        <p className="rounded-md bg-slate-100 px-4 py-3 text-sm text-slate-600">
          {session.status === 'escalated'
            ? 'The interview was stopped because of a red flag. The patient was told to seek urgent care.'
            : 'The patient has not submitted this history yet.'}
        </p>
      )}

      {showManual && <ManualEntry session={session} onSaved={setSession} />}

      {submitted && (
        <section className={cardClass}>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-800">History Summary</h2>
            {summary === null && (
              <button className="text-sm text-brand-600 hover:underline" onClick={() => setSummary(session.summary)}>
                Edit
              </button>
            )}
          </div>
          {summary === null ? (
            <p className="whitespace-pre-line text-slate-800">{session.summary}</p>
          ) : (
            <div className="space-y-2">
              <textarea className={inputClass} rows={5} value={summary} onChange={(e) => setSummary(e.target.value)} />
              <div className="flex justify-end gap-2">
                <button className={secondaryButton} onClick={() => setSummary(null)}>
                  Cancel
                </button>
                <button
                  className={primaryButton}
                  onClick={() => act(() => editHistorySummary(session.id, summary)).then(() => setSummary(null))}
                >
                  Save summary
                </button>
              </div>
            </div>
          )}
          <p className="mt-2 text-xs text-slate-400">
            {{ ai: 'Written by the AI assistant', auto: 'Built from the recorded fields', doctor: 'Edited by the doctor' }[
              session.summary_source
            ]}
          </p>
        </section>
      )}

      {submitted && (
        <section className={cardClass}>
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-slate-800">Structured history</h2>
            <span className="text-xs text-slate-500">{pending} field(s) awaiting review</span>
          </div>
          {Object.entries(groupBySection(session.fields)).map(([section, fields]) => (
            <div key={section} className="mb-4">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{section}</h3>
              {fields.map((f) => (
                <FieldRow
                  key={`${f.key}-${f.value}`}
                  field={f}
                  onAction={(action, value) => act(() => reviewHistoryField(session.id, f.key, action, value))}
                />
              ))}
            </div>
          ))}
        </section>
      )}

      {session.transcript.length > 0 && (
        <details className={cardClass}>
          <summary className="cursor-pointer text-sm font-semibold text-slate-800">
            Transcript ({session.transcript.length} messages)
          </summary>
          <ul className="mt-3 space-y-2 text-sm">
            {session.transcript.map((m, i) => (
              <li key={i} className={m.role === 'patient' ? 'text-slate-800' : 'text-slate-500'}>
                <span className="mr-2 text-xs text-slate-400">{formatTime(m.at)}</span>
                <b>{m.role === 'patient' ? 'Patient' : 'Assistant'}</b>
                {m.input === 'voice' && <span className="ml-1 text-xs text-slate-400">(spoken)</span>}: {m.text}
              </li>
            ))}
          </ul>
        </details>
      )}

      {session.edit_log.length > 0 && (
        <details className={cardClass}>
          <summary className="cursor-pointer text-sm font-semibold text-slate-800">Edit log ({session.edit_log.length})</summary>
          <ul className="mt-3 space-y-1.5 text-sm text-slate-700">
            {session.edit_log.map((e, i) => (
              <li key={i}>
                <span className="text-xs text-slate-400">
                  {formatDate(e.at)} {formatTime(e.at)}
                </span>{' '}
                {e.by_role} <b>{e.action}ed</b> {e.field.replaceAll('_', ' ')}
                {e.action === 'edit' && (
                  <>
                    : <span className="text-slate-400 line-through">{e.old || '(empty)'}</span> {'->'} {e.new}
                  </>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}
