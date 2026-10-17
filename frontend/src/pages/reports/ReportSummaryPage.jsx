import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  addSummaryTest,
  approveSummary,
  editSummaryTest,
  editSummaryText,
  fetchPageImage,
  getReport,
  getReportSummary,
  getSummaryTrends,
  removeSummaryTest,
} from '../../api/reports'
import { typeLabel } from '../../components/reports/reportMeta'
import { CONFIDENCE, RESULT_FLAG, SUMMARY_STATUS, sortTests } from '../../components/reports/summaryMeta'
import { cardClass, errorBox, errorMessage, formatDate, inputClass, primaryButton, secondaryButton } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { PATIENT_BASE } from '../../routes/roles'

/** Page images (as read by the AI) with a highlight on the selected value's printed location. */
function PageViewer({ reportId, version, count, selected }) {
  const [urls, setUrls] = useState([])
  const pageRefs = useRef([])

  useEffect(() => {
    let created = []
    Promise.all(Array.from({ length: count }, (_, i) => fetchPageImage(reportId, i + 1, version)))
      .then((blobs) => {
        created = blobs.map((b) => URL.createObjectURL(b))
        setUrls(created)
      })
      .catch(() => setUrls([]))
    return () => created.forEach((u) => URL.revokeObjectURL(u))
  }, [reportId, version, count])

  useEffect(() => {
    if (selected?.page) pageRefs.current[selected.page - 1]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [selected])

  if (!urls.length) return <p className="text-sm text-slate-500">Loading pages...</p>
  return (
    <div className="space-y-4">
      {urls.map((url, i) => (
        <div key={url} ref={(el) => (pageRefs.current[i] = el)} className="relative rounded-lg border border-slate-200 bg-white">
          <img src={url} alt={`Page ${i + 1}`} className="block w-full rounded-lg" />
          <span className="absolute left-2 top-2 rounded bg-slate-800/70 px-1.5 py-0.5 text-xs text-white">Page {i + 1}</span>
          {selected?.page === i + 1 && selected.bbox && (
            <div
              className="pointer-events-none absolute rounded border-2 border-red-600 bg-amber-300/25"
              style={{
                left: `${selected.bbox[0] / 10}%`,
                top: `${selected.bbox[1] / 10}%`,
                width: `${(selected.bbox[2] - selected.bbox[0]) / 10}%`,
                height: `${(selected.bbox[3] - selected.bbox[1]) / 10}%`,
              }}
            />
          )}
        </div>
      ))}
    </div>
  )
}

/** Tiny trend line for one analyte across approved reports (current value ringed). */
function Sparkline({ points }) {
  if (!points || points.length < 2) return null
  const w = 84, h = 24, pad = 4
  const values = points.map((p) => p.value)
  const [lo, hi] = [Math.min(...values), Math.max(...values)]
  const x = (i) => pad + (i / (points.length - 1)) * (w - 2 * pad)
  const y = (v) => h - pad - ((v - lo) / (hi - lo || 1)) * (h - 2 * pad)
  const title = points.map((p) => `${p.date}: ${p.value}${p.unit ? ` ${p.unit}` : ''}${p.current ? ' (this report)' : ''}`).join('\n')
  return (
    <svg width={w} height={h} className="shrink-0" role="img" aria-label={`Trend: ${title}`}>
      <title>{title}</title>
      <polyline fill="none" stroke="#1a5ea6" strokeWidth="2" strokeLinejoin="round" points={points.map((p, i) => `${x(i)},${y(p.value)}`).join(' ')} />
      {points.map((p, i) => (
        <circle key={i} cx={x(i)} cy={y(p.value)} r={p.current ? 3.5 : 2.5} fill={p.current ? '#ffffff' : '#1a5ea6'} stroke="#1a5ea6" strokeWidth="1.5" />
      ))}
    </svg>
  )
}

function TestRow({ test, trend, selected, onSelect, onSave, onRemove }) {
  const [draft, setDraft] = useState(null)
  const flag = RESULT_FLAG[test.flag]
  const conf = CONFIDENCE[test.confidence]

  if (draft) {
    return (
      <tr className="bg-brand-50">
        {['name', 'value', 'unit', 'reference_range'].map((k) => (
          <td key={k} className="p-1">
            <input className={`${inputClass} px-2 py-1`} value={draft[k] ?? ''} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
          </td>
        ))}
        <td colSpan={3} className="p-1 text-right">
          <button className="mr-2 text-xs text-brand-600 hover:underline" onClick={() => onSave(draft).then(() => setDraft(null))}>
            Save
          </button>
          <button className="text-xs text-slate-500 hover:underline" onClick={() => setDraft(null)}>
            Cancel
          </button>
        </td>
      </tr>
    )
  }
  return (
    <tr
      onClick={onSelect}
      className={`cursor-pointer border-b border-slate-100 ${selected ? 'bg-amber-50' : test.critical ? 'bg-red-50' : 'hover:bg-slate-50'}`}
    >
      <td className="px-2 py-2 font-medium text-slate-800">
        {test.name}
        {test.edited && <span className="ml-1 text-xs font-normal text-brand-600">edited</span>}
        {test.added_by_doctor && <span className="ml-1 text-xs font-normal text-brand-600">added</span>}
      </td>
      <td className="px-2 py-2">
        <b>{test.value}</b>
      </td>
      <td className="px-2 py-2 text-slate-600">{test.unit}</td>
      <td className="px-2 py-2 text-slate-600">{test.reference_range}</td>
      <td className={`px-2 py-2 ${flag?.className ?? ''}`}>{flag && `${flag.icon} ${flag.label}`}</td>
      <td className="px-2 py-2">
        {conf && <span className={`rounded px-1.5 py-0.5 text-xs ${conf.className}`}>{conf.label}</span>}
        <Sparkline points={trend} />
      </td>
      <td className="whitespace-nowrap px-2 py-2 text-right">
        <button className="mr-2 text-xs text-brand-600 hover:underline" onClick={(e) => {
            e.stopPropagation()
            setDraft(test)
          }}>
          Edit
        </button>
        <button className="text-xs text-red-600 hover:underline" onClick={(e) => {
            e.stopPropagation()
            onRemove()
          }}>
          Remove
        </button>
      </td>
    </tr>
  )
}

export default function ReportSummaryPage() {
  const { patientId, reportId } = useParams()
  const { user } = useAuth()
  const reportPath = `${PATIENT_BASE[user.role]}/${patientId}/reports/${reportId}`

  const [report, setReport] = useState(null)
  const [summary, setSummary] = useState(null)
  const [trends, setTrends] = useState({})
  const [selected, setSelected] = useState(null)
  const [text, setText] = useState(null) // editing draft of summary texts
  const [newRow, setNewRow] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([getReport(reportId), getReportSummary(reportId)])
      .then(([r, s]) => {
        setReport(r)
        setSummary(s)
        return getSummaryTrends(s.id).then(setTrends)
      })
      .catch((err) => setError(errorMessage(err, 'Could not load the summary')))
  }, [reportId])

  const run = async (action) => {
    setError('')
    try {
      const updated = await action()
      setSummary(updated)
      getSummaryTrends(updated.id).then(setTrends).catch(() => {})
      return true
    } catch (err) {
      setError(errorMessage(err, 'Could not save'))
      return false
    }
  }

  if (!summary || !report) return error ? <p className={errorBox}>{error}</p> : <p className="text-slate-500">Loading...</p>

  const imaging = summary.document_kind !== 'lab_report'
  const textFields = [
    ['summary_text', 'Summary'],
    ...(summary.findings != null || imaging ? [['findings', 'Findings']] : []),
    ...(summary.impression != null || imaging ? [['impression', 'Impression']] : []),
    ...(summary.image_observation != null ? [['image_observation', 'Preliminary AI observation']] : []),
  ]

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">{report.title || `${typeLabel(report.report_type)} report`}</h1>
          <p className="text-sm text-slate-500">
            <Link to={reportPath} className="text-brand-600 hover:underline">
              Back to report
            </Link>{' '}
            | {report.patient_name} | {formatDate(report.report_date)} | {SUMMARY_STATUS[summary.status]}
            {summary.approved_at && ` ${formatDate(summary.approved_at)} by ${summary.approved_by_role}`}
          </p>
        </div>
        {summary.status === 'ready' && (
          <button className={primaryButton} onClick={() => run(() => approveSummary(summary.id))}>
            Approve summary
          </button>
        )}
      </div>

      <p className="rounded-md border border-brand-200 bg-brand-50 px-4 py-2 text-sm text-brand-800">
        <b>{summary.label}</b> Readability: {summary.readability}; overall confidence: {summary.overall_confidence}. Only approved
        summaries reach the case summary, prescriptions and the patient. Editing an approved summary withdraws approval.
      </p>
      {summary.critical_values.length > 0 && (
        <p className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white">!! Critical values: {summary.critical_values.join('; ')}</p>
      )}
      {error && <p className={errorBox}>{error}</p>}

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto">
          <PageViewer reportId={reportId} version={summary.report_version} count={summary.page_count} selected={selected} />
        </section>

        <div className="space-y-5">
          <section className={cardClass}>
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-800">Summary</h2>
              {!text && (
                <button className="text-sm text-brand-600 hover:underline" onClick={() => setText(Object.fromEntries(textFields.map(([k]) => [k, summary[k] ?? ''])))}>
                  Edit
                </button>
              )}
            </div>
            {textFields.map(([key, label]) => (
              <div key={key} className="mb-3">
                <p className="text-xs font-medium text-slate-500">
                  {textFields.length > 1 && label}
                  {key === 'image_observation' && <span className="ml-1 text-red-700">(Assistive, not diagnostic. Requires doctor review.)</span>}
                </p>
                {text ? (
                  <textarea className={inputClass} rows={3} value={text[key]} onChange={(e) => setText({ ...text, [key]: e.target.value })} />
                ) : (
                  <p className="whitespace-pre-line text-sm text-slate-800">{summary[key] || '-'}</p>
                )}
              </div>
            ))}
            {text && (
              <div className="flex justify-end gap-2">
                <button className={secondaryButton} onClick={() => setText(null)}>
                  Cancel
                </button>
                <button className={primaryButton} onClick={() => run(() => editSummaryText(summary.id, text)).then((ok) => ok && setText(null))}>
                  Save
                </button>
              </div>
            )}
          </section>

          <section className={`${cardClass} p-0! overflow-x-auto`}>
            <div className="flex items-center justify-between px-4 py-3">
              <h2 className="text-sm font-semibold text-slate-800">Extracted values</h2>
              <span className="text-xs text-slate-500">Click a row to see where it is printed</span>
            </div>
            <table className="w-full text-left text-sm">
              <thead className="border-y border-slate-200 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-2 py-2">Test</th>
                  <th className="px-2 py-2">Value</th>
                  <th className="px-2 py-2">Unit</th>
                  <th className="px-2 py-2">Reference</th>
                  <th className="px-2 py-2">Flag</th>
                  <th className="px-2 py-2">AI confidence / trend</th>
                  <th className="px-2 py-2" />
                </tr>
              </thead>
              <tbody>
                {sortTests(summary.tests).map((t) => (
                  <TestRow
                    key={`${t.id}-${t.value}-${t.name}`}
                    test={t}
                    trend={trends[t.analyte_key]}
                    selected={selected?.id === t.id}
                    onSelect={() => setSelected(t)}
                    onSave={(draft) => run(() => editSummaryTest(summary.id, t.id, { name: draft.name, value: draft.value, unit: draft.unit || null, reference_range: draft.reference_range || null }))}
                    onRemove={() => run(() => removeSummaryTest(summary.id, t.id))}
                  />
                ))}
              </tbody>
            </table>
            {summary.tests.length === 0 && <p className="px-4 py-3 text-sm text-slate-400">No values extracted.</p>}
            <div className="px-4 py-3">
              {newRow ? (
                <div className="flex flex-wrap items-end gap-2">
                  {['name', 'value', 'unit', 'reference_range'].map((k) => (
                    <input key={k} className={`${inputClass} w-32!`} placeholder={k.replace('_', ' ')} value={newRow[k]} onChange={(e) => setNewRow({ ...newRow, [k]: e.target.value })} />
                  ))}
                  <button
                    className={primaryButton}
                    disabled={!newRow.name || !newRow.value}
                    onClick={() => run(() => addSummaryTest(summary.id, { ...newRow, unit: newRow.unit || null, reference_range: newRow.reference_range || null })).then((ok) => ok && setNewRow(null))}
                  >
                    Add
                  </button>
                  <button className="text-sm text-slate-500" onClick={() => setNewRow(null)}>
                    Cancel
                  </button>
                </div>
              ) : (
                <button className="text-sm text-brand-600 hover:underline" onClick={() => setNewRow({ name: '', value: '', unit: '', reference_range: '' })}>
                  + Add a value the AI missed
                </button>
              )}
            </div>
          </section>

          {selected?.source_text && (
            <p className="text-xs text-slate-500">
              Printed as: "{selected.source_text}" (page {selected.page}; highlighted location is approximate)
            </p>
          )}

          {summary.edit_log.length > 0 && (
            <details className={cardClass}>
              <summary className="cursor-pointer text-sm font-semibold text-slate-800">Edit log ({summary.edit_log.length})</summary>
              <ul className="mt-2 space-y-1 text-xs text-slate-600">
                {summary.edit_log.map((e, i) => (
                  <li key={i}>
                    {formatDate(e.at)} {e.by_role} {e.action} {e.field.replace('test:', '')}
                    {Object.entries(e.changes).map(([k, [before, after]]) => ` | ${k}: ${before ?? '-'} -> ${after ?? '-'}`).join('')}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </div>
    </div>
  )
}
