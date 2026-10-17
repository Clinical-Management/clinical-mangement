import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getReportSummary, runReportSummary } from '../../api/reports'
import { useAuth } from '../../context/AuthContext'
import { ROLES } from '../../routes/roles'
import { cardClass, formatDate, primaryButton, secondaryButton } from '../ui'
import { RESULT_FLAG, SUMMARY_STATUS, sortTests } from './summaryMeta'

function FlagText({ flag }) {
  const meta = RESULT_FLAG[flag]
  if (!meta || flag === 'normal') return null
  return (
    <span className={`ml-1 ${meta.className}`}>
      {meta.icon} {meta.label}
    </span>
  )
}

/** Report page card: doctors see status and the abnormal values; patients see an approved summary only. */
export default function SummaryCard({ reportId, reviewPath }) {
  const { user } = useAuth()
  const isPatient = user.role === ROLES.PATIENT
  const [summary, setSummary] = useState(undefined) // undefined = loading, null = none

  useEffect(() => {
    let timer
    const load = () =>
      getReportSummary(reportId)
        .then((s) => {
          setSummary(s)
          if (s.status === 'processing') timer = setTimeout(load, 4000) // AI is still reading
        })
        .catch(() => setSummary(null))
    load()
    return () => clearTimeout(timer)
  }, [reportId])

  if (summary === undefined) return null

  if (isPatient) {
    if (!summary) return null
    return (
      <section className={cardClass}>
        <h2 className="mb-1 text-sm font-semibold text-slate-800">Summary</h2>
        <p className="mb-3 text-xs text-slate-500">{summary.label}</p>
        <p className="whitespace-pre-line text-sm text-slate-800">{summary.summary_text}</p>
        {summary.impression && <p className="mt-2 text-sm text-slate-700">Impression: {summary.impression}</p>}
        {summary.tests.length > 0 && (
          <ul className="mt-3 space-y-1 text-sm">
            {sortTests(summary.tests).map((t, i) => (
              <li key={i}>
                {t.name}: <b>{t.value}</b> {t.unit}
                {t.reference_range && <span className="text-slate-500"> (normal {t.reference_range})</span>}
                <FlagText flag={t.flag} />
              </li>
            ))}
          </ul>
        )}
      </section>
    )
  }

  if (!summary) {
    return (
      <section className={cardClass}>
        <h2 className="mb-2 text-sm font-semibold text-slate-800">AI summary</h2>
        <button className={secondaryButton} onClick={() => runReportSummary(reportId).then(setSummary)}>
          Summarise with AI
        </button>
      </section>
    )
  }

  const abnormal = sortTests(summary.tests).filter((t) => t.flag && t.flag !== 'normal')

  return (
    <section className={cardClass}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-800">AI summary</h2>
        <span
          className={`rounded-full px-2 py-0.5 text-xs ${summary.status === 'approved' ? 'bg-accent-100 text-accent-700' : summary.status === 'failed' ? 'bg-red-100 text-red-700' : 'bg-slate-100 text-slate-600'}`}
        >
          {SUMMARY_STATUS[summary.status]}
        </span>
      </div>
      <p className="mb-2 text-xs text-slate-500">{summary.label}</p>
      {summary.critical_values.length > 0 && (
        <p className="mb-2 rounded-md bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
          !! Critical: {summary.critical_values.join('; ')}
        </p>
      )}
      {summary.summary_text && <p className="text-sm text-slate-800">{summary.summary_text}</p>}
      {abnormal.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-sm">
          {abnormal.slice(0, 6).map((t) => (
            <li key={t.id}>
              {t.name}: <b>{t.value}</b> {t.unit}
              <FlagText flag={t.flag} />
            </li>
          ))}
        </ul>
      )}
      {summary.error && <p className="mt-2 text-sm text-red-600">{summary.error}</p>}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {['ready', 'approved'].includes(summary.status) && (
          <Link to={reviewPath} className={primaryButton}>
            {summary.status === 'approved' ? 'View side by side' : 'Review and approve'}
          </Link>
        )}
        {['failed', 'ready', 'approved'].includes(summary.status) && (
          <button className="text-sm text-brand-600 hover:underline" onClick={() => runReportSummary(reportId).then(setSummary)}>
            Re-run AI
          </button>
        )}
        {summary.approved_at && <span className="text-xs text-slate-500">Approved {formatDate(summary.approved_at)} by {summary.approved_by_role}</span>}
      </div>
    </section>
  )
}
