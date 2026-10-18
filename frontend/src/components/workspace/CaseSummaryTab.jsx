import { useCallback, useEffect, useState } from 'react'
import {
  editCaseSummary,
  finalizeCaseSummary,
  generateCaseSummary,
  getCaseSummary,
  reopenCaseSummary,
  resolveSuggestion,
} from '../../api/caseSummary'
import useAutosave from '../../hooks/useAutosave'
import { cardClass, errorMessage, formatDate, formatTime, inputClass, primaryButton, secondaryButton } from '../ui'
import DiffText from './DiffText'
import SaveIndicator from './SaveIndicator'

const textsOf = (summary) => Object.fromEntries(summary.sections.map((s) => [s.key, s.text]))

export default function CaseSummaryTab({ appt, active = true }) {
  const [summary, setSummary] = useState(null)
  const [texts, setTexts] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [showChanges, setShowChanges] = useState(true)

  const final = summary?.status === 'final'
  const save = useCallback(async (t) => setSummary(await editCaseSummary(appt.id, t)), [appt.id])
  const autosave = useAutosave(texts, save, { enabled: texts !== null && !final })
  const { reset, flush } = autosave

  const load = useCallback(
    (s) => {
      const t = textsOf(s)
      reset(t)
      setTexts(t)
      setSummary(s)
    },
    [reset],
  )

  const run = useCallback(
    async (action) => {
      setBusy(true)
      setError('')
      try {
        await flush()
        load(await action())
      } catch (err) {
        setError(errorMessage(err, 'Something went wrong'))
      } finally {
        setBusy(false)
      }
    },
    [flush, load],
  )

  // Each time the tab is shown: create the first draft, or refresh a draft when new reports or notes arrived
  useEffect(() => {
    if (!active) return
    let cancelled = false
    getCaseSummary(appt.id)
      .then((s) => {
        if (cancelled) return
        if (s.stale && s.status === 'draft') run(() => generateCaseSummary(appt.id))
        else load(s)
      })
      .catch((err) => {
        if (cancelled) return
        if (err.response?.status === 404) run(() => generateCaseSummary(appt.id))
        else setError(errorMessage(err, 'Could not load the case summary'))
      })
    return () => {
      cancelled = true
    }
  }, [appt.id, load, run, active])

  if (!summary || !texts) return <p className="text-slate-500">{busy ? 'Writing the case summary...' : error || 'Loading...'}</p>

  const anyChange = summary.sections.some((s) => s.last_change?.some((o) => o.op !== 'equal'))
  const pendingSuggestions = summary.sections.filter((s) => s.suggestion).length

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm text-slate-600">
            <span className={`mr-2 rounded-full px-2 py-0.5 text-xs font-medium ${final ? 'bg-accent-100 text-accent-700' : 'bg-amber-100 text-amber-800'}`}>
              {final ? 'Finalized' : 'Draft'}
            </span>
            Version {summary.version} |{' '}
            {summary.generated_by === 'ai' ? 'Drafted by AI from the recorded data - review before finalizing' : 'Built from the recorded data'}
            {summary.finalized_at && ` | finalized ${formatDate(summary.finalized_at)} ${formatTime(summary.finalized_at)}`}
          </p>
          {summary.generation_note && <p className="text-xs text-slate-500">{summary.generation_note}</p>}
        </div>
        <div className="flex items-center gap-2">
          {!final && <SaveIndicator autosave={autosave} />}
          {!final && (
            <button className={secondaryButton} disabled={busy} onClick={() => run(() => generateCaseSummary(appt.id))}>
              Regenerate
            </button>
          )}
          {final ? (
            <button className={secondaryButton} disabled={busy} onClick={() => run(() => reopenCaseSummary(appt.id))}>
              Reopen to edit
            </button>
          ) : (
            <button className={primaryButton} disabled={busy || pendingSuggestions > 0} onClick={() => run(() => finalizeCaseSummary(appt.id))}>
              Finalize
            </button>
          )}
        </div>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {summary.stale && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          <p className="font-semibold">New information since this summary was written:</p>
          <ul className="mt-1 list-inside list-disc">
            {summary.pending_changes.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
          <button className={`${primaryButton} mt-3`} disabled={busy} onClick={() => run(() => generateCaseSummary(appt.id))}>
            Update the summary{final && ' (reopens it)'}
          </button>
        </div>
      )}

      {summary.version > 1 && summary.last_regeneration_changes.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-brand-50 px-4 py-2 text-sm text-brand-800">
          <span>Last updated because: {summary.last_regeneration_changes.join('; ')}</span>
          {anyChange && (
            <button className="underline" onClick={() => setShowChanges(!showChanges)}>
              {showChanges ? 'Hide changes' : 'Show what changed'}
            </button>
          )}
        </div>
      )}
      {pendingSuggestions > 0 && (
        <p className="text-sm text-amber-800">
          {pendingSuggestions} section(s) you edited have suggested updates. Accept or dismiss them before finalizing.
        </p>
      )}

      {summary.sections.map((s) => (
        <section key={s.key} className={cardClass}>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-800">{s.title}</h2>
            {s.edited && <span className="text-xs text-brand-600">edited by doctor</span>}
          </div>

          {showChanges && s.last_change?.some((o) => o.op !== 'equal') && !s.suggestion && (
            <div className="mb-2 rounded-md border border-dashed border-accent-600 bg-accent-50/40 p-2">
              <p className="mb-1 text-xs font-medium text-accent-700">Changed in the last update</p>
              <DiffText ops={s.last_change} />
            </div>
          )}

          {final ? (
            <p className="whitespace-pre-line text-sm text-slate-800">{s.text}</p>
          ) : (
            <textarea
              className={inputClass}
              rows={Math.min(10, Math.max(2, s.text.split('\n').length + 1))}
              value={texts[s.key]}
              onChange={(e) => setTexts({ ...texts, [s.key]: e.target.value })}
            />
          )}

          {s.suggestion && (
            <div className="mt-2 rounded-md border border-amber-300 bg-amber-50 p-3">
              <p className="mb-1 text-xs font-medium text-amber-900">Suggested update from new information (your text is kept until you accept)</p>
              <DiffText ops={s.suggestion.diff} />
              <div className="mt-2 flex gap-2">
                <button className={`${primaryButton} px-3 py-1 text-xs`} onClick={() => run(() => resolveSuggestion(appt.id, s.key, 'accept'))}>
                  Accept
                </button>
                <button className={`${secondaryButton} px-3 py-1 text-xs`} onClick={() => run(() => resolveSuggestion(appt.id, s.key, 'dismiss'))}>
                  Keep mine
                </button>
              </div>
            </div>
          )}
        </section>
      ))}
    </div>
  )
}
